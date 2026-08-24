from dataclasses import asdict, dataclass


@dataclass
class UserAccount:
    name: str
    email: str
    password: str
    title: str
    birth_date: str
    birth_month: str
    birth_year: str
    firstname: str
    lastname: str
    company: str
    address1: str
    address2: str
    country: str
    zipcode: str
    state: str
    city: str
    mobile_number: str

    def to_api_form(self) -> dict[str, str]:
        return asdict(self)
