from django.urls import path
from . import views


urlpatterns = [
    # Your existing endpoints
    path('upload-form-template/', views.upload_form_template),
    path('get_form_template/', views.get_form_template),
    
]