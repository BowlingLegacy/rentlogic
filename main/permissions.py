def user_role(user):
    if not user or not user.is_authenticated:
        return "anonymous"

    if user.is_superuser:
        return "super_admin"

    return getattr(user, "role", "resident")


# ROLE HELPERS

def is_resident(user):
    return user_role(user) in ["tenant", "resident"]



def is_landlord(user):
    return user_role(user) in ["landlord", "property_manager"]



def is_owner(user):
    return user_role(user) == "property_owner"



def is_assistant_admin(user):
    return user_role(user) in ["assistant", "assistant_admin"]



def is_super_admin(user):
    return user.is_authenticated and user.is_superuser


# ACCESS HELPERS

def can_access_landlord_dashboard(user):
    return (
        is_landlord(user)
        or is_owner(user)
        or is_assistant_admin(user)
        or is_super_admin(user)
    )



def can_access_owner_dashboard(user):
    return (
        is_owner(user)
        or is_assistant_admin(user)
        or is_super_admin(user)
    )



def can_create_resident_invite(user):
    return (
        is_landlord(user)
        or is_owner(user)
        or is_assistant_admin(user)
        or is_super_admin(user)
    )



def can_create_landlord(user):
    return (
        is_owner(user)
        or is_assistant_admin(user)
        or is_super_admin(user)
    )



def can_create_owner(user):
    return (
        is_assistant_admin(user)
        or is_super_admin(user)
    )



def can_delete_resident_files(user):
    return is_super_admin(user)



def can_access_django_admin(user):
    return is_super_admin(user)



def can_modify_platform_structure(user):
    return is_super_admin(user)
