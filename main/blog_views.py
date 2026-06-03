from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import BlogComment, BlogPost, HousingApplication, Property
from .permissions import is_assistant_admin, is_landlord, is_owner, is_super_admin


class BlogPostForm(forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ["property", "title", "body", "image"]
        widgets = {
            "property": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Post title"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 10, "placeholder": "Write the property update here..."}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["property"].queryset = manageable_properties(user)
        self.fields["property"].required = not can_manage_website_blog(user)
        if not can_manage_website_blog(user):
            self.fields["property"].empty_label = None


def can_manage_all_property_blogs(user):
    return is_super_admin(user) or is_assistant_admin(user)


def can_manage_website_blog(user):
    return is_super_admin(user)


def manageable_properties(user):
    if can_manage_all_property_blogs(user):
        return Property.objects.all().order_by("name")

    if is_owner(user):
        return Property.objects.filter(owner_email__iexact=user.email).order_by("name")

    if is_landlord(user):
        return Property.objects.filter(landlord_email__iexact=user.email).order_by("name")

    return Property.objects.none()


def can_manage_property_blog(user, property_obj):
    if can_manage_all_property_blogs(user):
        return True

    if not property_obj:
        return False

    if is_owner(user):
        return bool(property_obj.owner_email and property_obj.owner_email.lower() == user.email.lower())

    if is_landlord(user):
        return bool(property_obj.landlord_email and property_obj.landlord_email.lower() == user.email.lower())

    return False


def notify_property_residents_of_blog_post(request, post):
    if not post.property:
        return (0, 0)

    from .views import send_sms_message

    property_url = request.build_absolute_uri(f"{reverse('tenant_dashboard')}#property-updates")
    residents = (
        HousingApplication.objects
        .filter(property=post.property, user__isnull=False)
        .order_by("space_label", "full_name")
    )
    email_count = 0
    sms_count = 0

    for resident in residents:
        if resident.email:
            send_mail(
                f"New {post.property.name} community update: {post.title}",
                f"""Hello {resident.full_name},

A new community update has been posted for {post.property.name}.

Use this direct link. If you are not already signed in, the site will ask for your login first:
{property_url}

Thank you,
Bowling Legacy Housing
""",
                getattr(settings, "DEFAULT_FROM_EMAIL", None),
                [resident.email],
                fail_silently=False,
            )
            email_count += 1

        sms_log = send_sms_message(
            resident,
            (
                f"Bowling Legacy: New {post.property.name} community update posted. "
                f"Log in to view it: {property_url} Reply STOP to opt out."
            )[:1500],
            request.user,
        )
        if sms_log.status == "sent":
            sms_count += 1

    return email_count, sms_count


@login_required
def blog_manager(request):
    properties = manageable_properties(request.user)
    posts = (
        BlogPost.objects
        .select_related("property", "author")
        .filter(property__in=properties)
        .order_by("-created_at")
    )
    website_posts = BlogPost.objects.none()
    if can_manage_website_blog(request.user):
        website_posts = (
            BlogPost.objects
            .select_related("author")
            .filter(property__isnull=True)
            .order_by("-created_at")
        )

    if not properties.exists() and not can_manage_website_blog(request.user):
        return redirect("tenant_dashboard")

    pending_post_ids = list(posts.values_list("id", flat=True))
    if can_manage_website_blog(request.user):
        pending_post_ids.extend(website_posts.values_list("id", flat=True))

    pending_comments = BlogComment.objects.select_related("post", "post__property").filter(
        approved=False,
        post_id__in=pending_post_ids,
    )

    return render(request, "property_blog_manager.html", {
        "posts": posts,
        "website_posts": website_posts,
        "properties": properties,
        "pending_comments": pending_comments,
        "can_manage_website_blog": can_manage_website_blog(request.user),
    })


@login_required
def blog_create(request):
    if not manageable_properties(request.user).exists() and not can_manage_website_blog(request.user):
        return redirect("tenant_dashboard")

    form = BlogPostForm(request.POST or None, request.FILES or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)

        if post.property and not can_manage_property_blog(request.user, post.property):
            messages.error(request, "You do not have access to post for that property.")
            return redirect("property_blog_manager")
        if not post.property and not can_manage_website_blog(request.user):
            messages.error(request, "Only the superuser can post to the public website blog.")
            return redirect("property_blog_manager")

        post.author = request.user
        post.save()
        if post.property:
            email_count, sms_count = notify_property_residents_of_blog_post(request, post)
            messages.success(
                request,
                f"Property blog post created. Email notices sent to {email_count} resident(s). SMS sent to {sms_count} opted-in resident(s).",
            )
        else:
            messages.success(request, "Public website blog post created.")
        return redirect("property_blog_manager")

    return render(request, "property_blog_form.html", {"form": form})


@login_required
def approve_blog_comment(request, comment_id):
    comment = get_object_or_404(BlogComment.objects.select_related("post", "post__property"), id=comment_id)

    if comment.post.property:
        can_manage_comment = can_manage_property_blog(request.user, comment.post.property)
    else:
        can_manage_comment = can_manage_website_blog(request.user)

    if not can_manage_comment:
        return redirect("tenant_dashboard")

    comment.approved = True
    comment.save(update_fields=["approved"])
    messages.success(request, "Comment approved.")
    return redirect("property_blog_manager")


@login_required
def delete_blog_comment(request, comment_id):
    comment = get_object_or_404(BlogComment.objects.select_related("post", "post__property"), id=comment_id)

    if comment.post.property:
        can_manage_comment = can_manage_property_blog(request.user, comment.post.property)
    else:
        can_manage_comment = can_manage_website_blog(request.user)

    if not can_manage_comment:
        return redirect("tenant_dashboard")

    if request.method == "POST":
        comment.delete()
        messages.success(request, "Comment deleted.")

    return redirect("property_blog_manager")
