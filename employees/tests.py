from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from django.utils import timezone
from tasks.models import Task
from reports.models import Report
from employees.models import SiteData

User = get_user_model()

class EmployeeAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.employee = User.objects.create_user(
            username="Employee",
            password="sanjay123",
            email="employee@example.com",
            role="employee",
            state="Andhra Pradesh",
            user_type="employee"
        )
        self.client.force_authenticate(user=self.employee)
        self.site = SiteData.objects.create(
            global_id="TEST001",
            cluster_name="Vizag",
            site_name="Steel Plant",
            latitude=17.7,
            longitude=83.3
        )
        self.task = Task.objects.create(
            task_id=100001,
            global_id=self.site.global_id,
            cluster_name=self.site.cluster_name,
            site_name=self.site.site_name,
            latitude=self.site.latitude,
            longitude=self.site.longitude,
            assigned_to=self.employee,
            task_type="DG PM",
            state=self.employee.state,
            assigned_date=timezone.now()
        )
        self.client = APIClient()
        self.client.login(username="Employee", password="sanjay123")

    def test_dashboard(self):
        response = self.client.get('/employee/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_my_tasks(self):
        response = self.client.get('/employee/my-tasks/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) >= 1)

    def test_submit_report(self):
        data = {
            "task_id": self.task.id,
            "form_data": {
                "DG Status": "Running",
                "Battery Health": "Good"
            }
        }
        response = self.client.post('/employee/submit-report/', data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn("report_id", response.data)
