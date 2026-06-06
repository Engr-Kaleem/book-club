"""
Tests for book CRUD operations and search.
"""


class TestBookCRUD:
    """Tests for basic book create/read/update/delete."""

    def test_create_book(self, client):
        response = client.post("/books", json={
            "title": "Test Book",
            "author": "Test Author",
            "description": "A test book",
            "published_date": "2020-01-01",
            "page_count": 200,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Book"
        assert data["author"] == "Test Author"
        assert data["page_count"] == 200

    def test_get_book(self, client, sample_books):
        response = client.get(f"/books/{sample_books[0].id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "The Shining"
        assert data["author"] == "Stephen King"

    def test_get_book_not_found(self, client):
        response = client.get("/books/9999")
        assert response.status_code == 404

    def test_list_books(self, client, sample_books):
        response = client.get("/books")
        assert response.status_code == 200
        data = response.json()
        # Works with both plain list (pre-Ticket 4) and paginated dict (post-Ticket 4)
        items = data["items"] if isinstance(data, dict) else data
        assert len(items) == 6

    def test_update_book(self, client, sample_books):
        response = client.put(f"/books/{sample_books[0].id}", json={
            "title": "The Shining (Updated Edition)",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "The Shining (Updated Edition)"
        # Other fields should remain unchanged
        assert data["author"] == "Stephen King"

    def test_delete_book(self, client, sample_books):
        response = client.delete(f"/books/{sample_books[2].id}")
        assert response.status_code == 204
        # Verify it's gone
        response = client.get(f"/books/{sample_books[2].id}")
        assert response.status_code == 404

    def test_create_book_invalid_date_format(self, client):
        response = client.post("/books", json={
            "title": "Bad Date Book",
            "author": "Some Author",
            "published_date": "not-a-date",
        })
        assert response.status_code == 422

    def test_create_book_empty_title(self, client):
        response = client.post("/books", json={
            "title": "",
            "author": "Some Author",
        })
        assert response.status_code == 422


class TestBookSearch:
    """Tests for book search functionality."""

    def test_search_by_title(self, client, sample_books):
        response = client.get("/books/search?q=shining")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(b["title"] == "The Shining" for b in data)

    def test_search_empty_query(self, client):
        response = client.get("/books/search?q=")
        assert response.status_code == 400

    def test_search_results_are_unique(self, client, sample_books):
        response = client.get("/books/search?q=king")
        assert response.status_code == 200

        data = response.json()
        ids = [book["id"] for book in data]
        assert len(ids) == len(set(ids))

    def test_search_endpoint_dedupes_service_results(self, client, sample_books, monkeypatch):
        def fake_search_books(db, query):
            return [sample_books[0], sample_books[0], sample_books[1]]

        monkeypatch.setattr("bookclub.app.services.search_books", fake_search_books)

        response = client.get("/books/search?q=king")
        assert response.status_code == 200

        data = response.json()
        ids = [book["id"] for book in data]
        assert ids == [sample_books[0].id, sample_books[1].id]

