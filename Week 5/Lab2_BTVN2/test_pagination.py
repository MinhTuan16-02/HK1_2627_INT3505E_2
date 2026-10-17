"""Run inside Lab2_BTVN2: python -m unittest -v test_pagination.py"""

import base64
import json
import unittest
from urllib.parse import urlencode

from app import create_app, db


class BookPaginationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SEED_DATA": True,
        })
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def get(self, **params):
        return self.client.get(
            "/api/v1/books?" + urlencode(params)
        )

    def encode_cursor(self, state):
        payload = json.dumps(
            state,
            separators=(",", ":")
        ).encode("utf-8")

        return (
            base64.urlsafe_b64encode(payload)
            .decode("ascii")
            .rstrip("=")
        )

    def test_01_offset_pagination(self):
        first = self.get(
            strategy="offset",
            offset=0,
            limit=5,
            sort="id",
        )

        self.assertEqual(first.status_code, 200)

        data = first.get_json()

        self.assertEqual(
            data["pagination"],
            {
                "offset": 0,
                "limit": 5,
                "total": 12,
                "has_next": True,
            },
        )

        self.assertEqual(
            [book["id"] for book in data["data"]],
            [
                "book_1",
                "book_2",
                "book_3",
                "book_4",
                "book_5",
            ],
        )

        second = self.get(
            strategy="offset",
            offset=5,
            limit=5,
            sort="id",
        )

        self.assertEqual(second.status_code, 200)

        second_data = second.get_json()

        self.assertEqual(
            second_data["data"][0]["id"],
            "book_6",
        )

    def test_02_cursor_page1_to_page2(self):
        first = self.get(
            strategy="cursor",
            limit=3,
            sort="-price",
        )

        self.assertEqual(first.status_code, 200)

        page1 = first.get_json()

        self.assertTrue(page1["page"]["more"])

        token = page1["page"]["next"]

        self.assertIsInstance(token, str)

        second = self.get(
            strategy="cursor",
            limit=3,
            sort="-price",
            cursor=token,
        )

        self.assertEqual(second.status_code, 200)

        page2 = second.get_json()

        ids1 = {
            book["id"]
            for book in page1["data"]
        }

        ids2 = {
            book["id"]
            for book in page2["data"]
        }

        self.assertFalse(ids1 & ids2)
        self.assertEqual(len(page2["data"]), 3)

    def test_03_filter_genre(self):
        response = self.get(
            strategy="offset",
            genre="tech",
            limit=20,
        )

        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        self.assertEqual(
            data["pagination"]["total"],
            6,
        )

        self.assertTrue(
            all(
                book["category"]["slug"] == "tech"
                for book in data["data"]
            )
        )

        empty = self.get(
            strategy="offset",
            genre="unknown",
        )

        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.get_json()["data"], [])

    def test_04_filter_category(self):
        response = self.get(
            strategy="offset",
            category=1,
            limit=20,
        )

        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        self.assertEqual(
            data["pagination"]["total"],
            6,
        )

        self.assertTrue(
            all(
                book["category"]["id"] == 1
                for book in data["data"]
            )
        )

    def test_05_multikey_sort_and_no_missing_ties(self):
        token = None
        result = []

        for _ in range(20):
            params = {
                "strategy": "cursor",
                "sort": "-price,title",
                "genre": "tech",
                "limit": 2,
            }

            if token is not None:
                params["cursor"] = token

            response = self.get(**params)

            self.assertEqual(
                response.status_code,
                200,
            )

            obj = response.get_json()

            result.extend(obj["data"])

            if not obj["page"]["more"]:
                self.assertIsNone(
                    obj["page"]["next"]
                )
                break

            token = obj["page"]["next"]

        self.assertEqual(len(result), 6)

        self.assertEqual(
            len({
                book["id"]
                for book in result
            }),
            6,
        )

        expected = sorted(
            result,
            key=lambda book: (
                -book["price"]["amount"],
                book["title"],
                int(
                    book["id"]
                    .split("_")[1]
                ),
            ),
        )

        self.assertEqual(
            result,
            expected,
        )

        response = self.get(
            strategy="cursor",
            sort="price,-id",
            limit=20,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.get_json()["data"]

        expected = sorted(
            data,
            key=lambda book: (
                book["price"]["amount"],
                -int(
                    book["id"]
                    .split("_")[1]
                ),
            ),
        )

        self.assertEqual(
            data,
            expected,
        )

    def test_06_default_sort_is_descending_id(self):
        response = self.get(
            strategy="cursor",
            limit=3,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.get_json()["data"]

        self.assertEqual(
            [book["id"] for book in data],
            [
                "book_12",
                "book_11",
                "book_10",
            ],
        )

    def test_07_reject_unknown_sort(self):
        response = self.get(
            sort="foo"
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_sort"
            },
        )

    def test_08_reject_sort_changed_mid_cursor(self):
        first = self.get(
            strategy="cursor",
            sort="-price",
            limit=2,
        )

        token = (
            first.get_json()
            ["page"]
            ["next"]
        )

        response = self.get(
            strategy="cursor",
            sort="title",
            limit=2,
            cursor=token,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "sort_chg"
            },
        )

    def test_09_reject_malformed_cursor(self):
        response = self.get(
            strategy="cursor",
            cursor="broken",
            limit=2,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_cursor"
            },
        )

    def test_10_reject_filter_change(self):
        first = self.get(
            strategy="cursor",
            genre="tech",
            sort="price",
            limit=2,
        )

        token = (
            first.get_json()
            ["page"]
            ["next"]
        )

        response = self.get(
            strategy="cursor",
            genre="fiction",
            sort="price",
            cursor=token,
            limit=2,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "filter_chg"
            },
        )

    def test_11_reject_offset_with_cursor(self):
        response = self.get(
            strategy="offset",
            offset=0,
            cursor="abc",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_cursor"
            },
        )

    def test_12_reject_cursor_with_offset(self):
        response = self.get(
            strategy="cursor",
            offset=1,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_offset"
            },
        )

    def test_13_validate_normal_parameters(self):
        cases = [
            (
                {
                    "limit": "0"
                },
                "bad_limit",
            ),
            (
                {
                    "strategy": "offset",
                    "offset": "-1",
                },
                "bad_offset",
            ),
            (
                {
                    "strategy": "oops"
                },
                "bad_strategy",
            ),
            (
                {
                    "sort": "id,id"
                },
                "bad_sort",
            ),
            (
                {
                    "genre": "Tech!"
                },
                "bad_genre",
            ),
        ]

        for params, expected_error in cases:
            with self.subTest(
                params=params
            ):
                response = self.get(
                    **params
                )

                self.assertEqual(
                    response.status_code,
                    400,
                )

                self.assertEqual(
                    response.get_json()
                    ["error"],
                    expected_error,
                )

    def test_14_large_numbers_return_400(self):
        huge = str(
            2**31
        )

        cases = [
            (
                {
                    "strategy": "offset",
                    "offset": huge,
                },
                "bad_offset",
            ),
            (
                {
                    "strategy": "offset",
                    "category": huge,
                },
                "bad_category",
            ),
        ]

        for params, expected_error in cases:
            with self.subTest(
                params=params
            ):
                response = self.get(
                    **params
                )

                self.assertEqual(
                    response.status_code,
                    400,
                )

                self.assertEqual(
                    response.get_json()
                    ["error"],
                    expected_error,
                )

    def test_15_reject_cursor_with_huge_id(self):
        token = self.encode_cursor({
            "s": "-id",
            "v": [],
            "i": 2**31,
            "f": {
                "genre": None,
                "category": None,
            },
        })

        response = self.get(
            strategy="cursor",
            cursor=token,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_cursor"
            },
        )

    def test_16_reject_cursor_with_huge_price(self):
        token = self.encode_cursor({
            "s": "-price",
            "v": [
                2**31
            ],
            "i": 1,
            "f": {
                "genre": None,
                "category": None,
            },
        })

        response = self.get(
            strategy="cursor",
            sort="-price",
            cursor=token,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_cursor"
            },
        )

    def test_17_reject_cursor_wrong_value_type(self):
        token = self.encode_cursor({
            "s": "-price",
            "v": [
                "620000"
            ],
            "i": 4,
            "f": {
                "genre": None,
                "category": None,
            },
        })

        response = self.get(
            strategy="cursor",
            sort="-price",
            cursor=token,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.get_json(),
            {
                "error": "bad_cursor"
            },
        )

    def test_18_limit_is_capped_at_100_offset(self):
        response = self.get(
            strategy="offset",
            limit=500,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.get_json()

        self.assertEqual(
            data["pagination"]["limit"],
            100,
        )

    def test_19_limit_is_capped_at_100_cursor(self):
        response = self.get(
            strategy="cursor",
            limit=500,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.get_json()

        self.assertEqual(
            len(data["data"]),
            12,
        )

        self.assertFalse(
            data["page"]["more"]
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )