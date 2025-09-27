from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
import re


class User(AbstractUser):
    CIRCLE_CHOICES = [
        ("Andhra Pradesh", "Andhra Pradesh"),
        ("Tamil Nadu", "Tamil Nadu"),
        ("Odisha", "Odisha"),
    ]

    ROLE_CHOICES = [
        ("superadmin", "SuperAdmin"),
        ("admin", "Admin"),
        ("employee", "Employee"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    circle = models.CharField(
        max_length=100,
        choices=CIRCLE_CHOICES,
        blank=True,
        null=True,   # 🔑 superadmin can have no circle
    )

    global_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    state_user_id = models.CharField(max_length=30, unique=False, blank=True, null=True)

    passport_photo = models.ImageField(upload_to="passport_photos/", blank=True, null=True)
    signature_photo = models.ImageField(upload_to="signature_photos/", blank=True, null=True)

    reset_otp = models.CharField(max_length=6, blank=True, null=True)
    reset_otp_created_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        """Custom validation: enforce circle for admins and employees."""
        super().clean()
        if self.role in ["admin", "employee"] and not self.circle:
            raise ValidationError({"circle": "Circle is required for admins and employees."})

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if is_new or (not self.state_user_id and self.role):
            # --- Global ID generation ---
            if not self.global_id:
                with transaction.atomic():
                    last_user = User.objects.select_for_update().order_by("-id").first()
                    next_id = (last_user.id if last_user else 0) + 1
                    self.global_id = f"USR-{next_id:04d}"

            # --- Circle User ID generation ---
            if not self.state_user_id:
                if self.role == "superadmin":
                    prefix = self.circle[:2].upper() if self.circle else "GEN"
                    role_code = "SUP"
                elif self.role == "admin":
                    prefix = self.circle[:2].upper() if self.circle else "NA"
                    role_code = "ADM"
                else:  # employee
                    prefix = self.circle[:2].upper() if self.circle else "NA"
                    role_code = "EMP"

                count = 1
                while True:
                    if prefix == "GEN" and self.role == "superadmin":
                        potential_id = f"{role_code}-{count:03d}"  # SUP-001
                    else:
                        potential_id = f"{prefix}-{role_code}-{count:03d}"  # TN-ADM-001
                    if not User.objects.filter(state_user_id=potential_id).exists():
                        self.state_user_id = potential_id
                        break
                    count += 1

        super().save(*args, **kwargs)

    # --- Password Strength Validation ---
    @staticmethod
    def validate_password_strength(password):
        """
        Custom password validation:
        - At least 8 characters
        - At least 1 uppercase letter
        - At least 1 number
        - At least 1 special character
        """
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", password):
            raise ValidationError("Password must contain at least one number.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise ValidationError("Password must contain at least one special character.")

    # --- OTP Reset Handling ---
    def is_reset_otp_valid(self, otp):
        """Check OTP correctness and 10 min expiry."""
        if not self.reset_otp or not self.reset_otp_created_at:
            return False
        if str(self.reset_otp) != str(otp):
            return False
        expiry_time = self.reset_otp_created_at + timedelta(minutes=10)
        return timezone.now() <= expiry_time
