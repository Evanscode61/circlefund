from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase

from accounts.models import User
from chamas.models import Group
from chamas.services import assign_role, create_group


class CreateGroupTests(APITestCase):
    url = "/api/v1/groups/"

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="evans", password="pass12345", phone="+254712345678"
        )

    def test_requires_login(self) -> None:
        response = self.client.post(self.url, {"name": "Umoja", "group_type": "chama"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_creates_group_with_owner(self) -> None:
        self.client.force_authenticate(self.user)
        response = self.client.post(
            self.url,
            {"name": "Umoja Women Chama", "group_type": "chama", "phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        group = Group.objects.get(slug="umoja-women-chama")
        self.assertEqual(group.phone_number, "+254712345678")
        membership = group.memberships.get(user=self.user)
        self.assertEqual(membership.role.name, "Owner")
        self.assertEqual(membership.member_number, "0001")

    def test_rejects_bad_phone(self) -> None:
        self.client.force_authenticate(self.user)
        response = self.client.post(
            self.url,
            {"name": "Umoja", "group_type": "chama", "phone_number": "abc"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone_number", response.data["errors"])


class MyGroupsTests(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="evans2", password="pass12345", phone="+254711111111")
        self.other = User.objects.create_user(username="amina", password="pass12345", phone="+254722222222")
        create_group(user=self.user, name="Umoja Women Chama", group_type="chama")
        create_group(user=self.other, name="Other Group", group_type="chama")

    def test_lists_only_my_groups(self) -> None:
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/groups/")
        self.assertEqual(response.status_code, 200)
        slugs = [item["group"]["slug"] for item in response.data["data"]]
        self.assertEqual(slugs, ["umoja-women-chama"])

    def test_list_uses_one_query(self) -> None:
        create_group(user=self.user, name="Second Group", group_type="chama")
        create_group(user=self.user, name="Third Group", group_type="chama")
        self.client.force_authenticate(self.user)
        with self.assertNumQueries(1):
            self.client.get("/api/v1/groups/")

    def test_detail_for_member(self) -> None:
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/groups/umoja-women-chama/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["membership"]["role"], "Owner")
        self.assertIn("loans.approve", response.data["data"]["permissions"])

    def test_detail_hidden_from_non_member(self) -> None:
        self.client.force_authenticate(self.other)
        response = self.client.get("/api/v1/groups/umoja-women-chama/")
        self.assertEqual(response.status_code, 404)


class AssignRoleTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="evans3", password="pass12345", phone="+254733333333")
        self.group = create_group(user=self.user, name="Group One", group_type="chama")
        self.other = create_group(user=self.user, name="Group Two", group_type="chama")
        self.membership = self.group.memberships.get(user=self.user)

    def test_assigns_role_from_same_group(self) -> None:
        assign_role(self.membership, self.group.roles.get(name="Treasurer"))
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role.name, "Treasurer")

    def test_rejects_role_from_other_group(self) -> None:
        with self.assertRaises(ValidationError):
            assign_role(self.membership, self.other.roles.get(name="Owner"))