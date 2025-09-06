from django.db import models
from django.conf import settings

class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
        null=True,  # <--- add this
        blank=True
    )
    company_name = models.CharField(max_length=255, blank=True, null=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    passport_photo = models.ImageField(upload_to="employee/passports/", blank=True, null=True)
    signature_photo = models.ImageField(upload_to="employee/signatures/", blank=True, null=True)
    mobile_number = models.CharField(max_length=15, blank=True, null=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="team_members",
        blank=True,
        null=True
    )  # L1 User ID reference
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.first_name} ({self.employee_id or 'No ID'})"
