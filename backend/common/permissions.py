from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsManager(BasePermission):
    """Allow an action only to an authenticated warehouse Manager."""

    message = "Only managers may perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_manager
        )


class IsManagerOrReadOnly(BasePermission):
    """Anyone signed in may read; only managers may write.

    Operators work the floor: they read inventory and record stock movements
    (which have their own endpoint). Suppliers, pricing and purchase orders
    are commercial decisions and stay with managers.
    """

    message = "Only managers may change this."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_manager
