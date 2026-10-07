from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("appareils/", views.AppareilView.as_view(), name="appareils"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("notifications/<int:pk>/lu/", views.NotificationLueView.as_view(), name="notification-lue"),
]
