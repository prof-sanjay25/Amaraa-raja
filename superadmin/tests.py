from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from authentication.models import User

class SuperAdminAPITests(APITestCase):
    def setUp(self):
        self.superadmin = User.objects.create_user(
            username="test",
            email="test@example.com",
            password="test123",
            role="superadmin",
            state="Global"
        )

        self.client = APIClient()
        login = self.client.post('/auth/login/', {
            'username': 'test',
            'password': 'test123'
        })

        self.assertEqual(login.status_code, 200)
        self.token = login.data['access']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.token)

    def test_dashboard_view(self):
        res = self.client.get('/superadmin/api/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_admin(self):
        res = self.client.post('/superadmin/api/admins/', {
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin1@example.com",
            "state": "Telangana",
            "password": "admin123",
            "confirm_password": "admin123"
        })
        self.assertEqual(res.status_code, 201)

    def test_create_employee(self):
        res = self.client.post('/superadmin/api/employees/', {
            "first_name": "Emp",
            "last_name": "User",
            "email": "emp1@example.com",
            "state": "Odisha",
            "password": "emp123",
            "confirm_password": "emp123"
        })
        self.assertEqual(res.status_code, 201)

    def test_profile_view(self):
        res = self.client.get('/superadmin/api/profile/')
        self.assertEqual(res.status_code, 200)

    def test_profile_update(self):
        res = self.client.put('/superadmin/api/profile/update/', {
            "first_name": "Chief",
            "email": "chief@example.com"
        }, format='json')
        self.assertEqual(res.status_code, 200)

    def test_summary_view(self):
        self.test_create_admin()
        self.test_create_employee()
        res = self.client.get('/superadmin/api/summary/statewise/')
        self.assertEqual(res.status_code, 200)

    def test_list_all_tasks_empty(self):
        res = self.client.get('/superadmin/api/tasks/')
        self.assertEqual(res.status_code, 200)
