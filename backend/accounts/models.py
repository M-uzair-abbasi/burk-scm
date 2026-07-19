from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Warehouse user.

    Module 3 distinguishes packing operators from managers, so the role split
    exists from the first migration rather than being retrofitted later.
    """

    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        OPERATOR = "operator", "Operator"

    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.OPERATOR,
    )

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER or self.is_superuser
