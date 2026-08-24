from faker import Faker

from ecom_taf.models.user import UserAccount

_fake = Faker()


class UserFactory:
    @staticmethod
    def build(*, email: str | None = None, password: str = "Qwerty!234") -> UserAccount:
        first = _fake.first_name()
        last = _fake.last_name()
        unique_email = (
            email
            or f"{first.lower()}.{last.lower()}.{_fake.unique.random_int(1000, 99999)}@example.com"
        )
        return UserAccount(
            name=f"{first} {last}",
            email=unique_email,
            password=password,
            title=_fake.random_element(["Mr", "Mrs", "Miss"]),
            birth_date=str(_fake.random_int(1, 28)),
            birth_month=str(_fake.random_int(1, 12)),
            birth_year=str(_fake.random_int(1970, 2000)),
            firstname=first,
            lastname=last,
            company=_fake.company(),
            address1=_fake.street_address(),
            address2=_fake.secondary_address(),
            country="United States",
            zipcode=_fake.postcode(),
            state=_fake.state(),
            city=_fake.city(),
            mobile_number=_fake.numerify("##########"),
        )
