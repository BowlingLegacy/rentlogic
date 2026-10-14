from django.contrib import admin
from django.urls import path, include, re_path
from main.media_views import secure_media

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("main.urls")),
]

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", secure_media),
]
