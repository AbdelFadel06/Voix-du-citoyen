import django_filters

from .models import Notification


class NotificationFilter(django_filters.FilterSet):
    lu = django_filters.BooleanFilter(
        help_text="`false` : notifications non lues seulement (`pagination.total` donne leur nombre, "
        "par exemple pour un badge)."
    )
    type = django_filters.ChoiceFilter(choices=Notification.Type.choices, help_text="Nature de l'événement.")

    class Meta:
        model = Notification
        fields = ["lu", "type"]
