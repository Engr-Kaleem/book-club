"""
FastAPI application: route definitions, middleware, startup.

This is the main entry point for the BookClub API. Start with:

    uvicorn app:app --reload

Then visit http://localhost:8000/docs for interactive API documentation.
"""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from bookclub.auth import get_current_user_id, rate_limiter, require_auth
from bookclub.database import get_db, init_db
from bookclub.schemas import (
    BookCreate,
    BookResponse,
    BookUpdate,
    ReadingListCreate,
    ReadingListDetailResponse,
    ReadingListItemCreate,
    ReadingListItemResponse,
    ReadingListResponse,
    ReviewCreate,
    ReviewResponse,
    UserCreate,
    UserResponse,
)
from bookclub.seed_data import seed_database
from bookclub import services


app = FastAPI(
    title="BookClub API",
    description="A team book club service for tracking books, reading lists, and reviews.",
    version="1.0.0",
)


@app.on_event("startup")
def startup():
    """Initialize the database and seed with sample data on first run."""
    init_db()
    # Seed if the database is empty
    from bookclub.database import SessionLocal
    db = SessionLocal()
    try:
        from bookclub.models import User
        if db.query(User).count() == 0:
            seed_database(db)
    finally:
        db.close()


# ===========================================================================
# User endpoints
# ===========================================================================

@app.get("/users", response_model=list[UserResponse], tags=["Users"])
def list_users(db: Session = Depends(get_db)):
    """List all registered users."""
    return services.get_users(db)


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a user by ID."""
    user = services.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/users", response_model=UserResponse, status_code=201, tags=["Users"])
def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    existing = services.get_user_by_username(db, user_data.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")
    return services.create_user(
        db,
        username=user_data.username,
        email=user_data.email,
        display_name=user_data.display_name,
    )


# ===========================================================================
# Book endpoints
# ===========================================================================

@app.get("/books", response_model=list[BookResponse], tags=["Books"])
def list_books(db: Session = Depends(get_db)):
    """
    List all books in the catalog.
    """
    return services.get_books(db)


@app.get("/books/search", response_model=list[BookResponse], tags=["Books"])
def search_books(q: str, db: Session = Depends(get_db)):
    """Search books by title, author, or description."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    # Defensive dedupe at API boundary in case lower layers return repeats.
    results = services.search_books(db, q.strip())
    unique_results = []
    seen_ids = set()
    for book in results:
        if book.id in seen_ids:
            continue
        seen_ids.add(book.id)
        unique_results.append(book)

    return unique_results


@app.get("/books/{book_id}", response_model=BookResponse, tags=["Books"])
def get_book(book_id: int, db: Session = Depends(get_db)):
    """Get a book by ID."""
    book = services.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.post("/books", response_model=BookResponse, status_code=201, tags=["Books"])
def create_book(book_data: BookCreate, db: Session = Depends(get_db)):
    """Add a new book to the catalog."""
    return services.create_book(
        db,
        title=book_data.title,
        author=book_data.author,
        description=book_data.description,
        published_date=book_data.published_date,
        isbn=book_data.isbn,
        page_count=book_data.page_count,
    )


@app.put("/books/{book_id}", response_model=BookResponse, tags=["Books"])
def update_book(book_id: int, book_data: BookUpdate, db: Session = Depends(get_db)):
    """Update a book's details."""
    updated = services.update_book(
        db,
        book_id,
        title=book_data.title,
        author=book_data.author,
        description=book_data.description,
        published_date=book_data.published_date,
        isbn=book_data.isbn,
        page_count=book_data.page_count,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return updated


@app.delete("/books/{book_id}", status_code=204, tags=["Books"])
def delete_book(book_id: int, db: Session = Depends(get_db)):
    """Delete a book from the catalog."""
    if not services.delete_book(db, book_id):
        raise HTTPException(status_code=404, detail="Book not found")


# ===========================================================================
# Review endpoints
# ===========================================================================

@app.get(
    "/books/{book_id}/reviews",
    response_model=list[ReviewResponse],
    tags=["Reviews"],
)
def list_reviews(book_id: int, db: Session = Depends(get_db)):
    """List all reviews for a book."""
    book = services.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return services.get_reviews_for_book(db, book_id)


@app.post(
    "/books/{book_id}/reviews",
    response_model=ReviewResponse,
    status_code=201,
    tags=["Reviews"],
)
def create_review(
    book_id: int,
    review_data: ReviewCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_auth),
):
    """
    Create a review for a book. Requires authentication.
    """
    book = services.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        return services.create_review(
            db,
            user_id=user_id,
            book_id=book_id,
            rating=review_data.rating,
            text=review_data.text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================================================
# Reading List endpoints
# ===========================================================================

@app.get(
    "/users/{user_id}/lists",
    response_model=list[ReadingListResponse],
    tags=["Reading Lists"],
)
def list_reading_lists(user_id: int, db: Session = Depends(get_db)):
    """List all reading lists for a user."""
    user = services.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return services.get_reading_lists_for_user(db, user_id)


@app.post(
    "/users/{user_id}/lists",
    response_model=ReadingListResponse,
    status_code=201,
    tags=["Reading Lists"],
)
def create_reading_list(
    user_id: int,
    list_data: ReadingListCreate,
    db: Session = Depends(get_db),
    auth_user_id: int = Depends(require_auth),
):
    """Create a new reading list. Requires authentication as the list owner."""
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only create lists for yourself")
    user = services.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return services.create_reading_list(
        db, user_id=user_id, name=list_data.name, description=list_data.description
    )


@app.get(
    "/users/{user_id}/lists/{list_id}",
    response_model=ReadingListDetailResponse,
    tags=["Reading Lists"],
)
def get_reading_list(
    user_id: int, list_id: int, db: Session = Depends(get_db)
):
    """Get a reading list with all its items."""
    reading_list = services.get_reading_list(db, list_id)
    if reading_list is None or reading_list.user_id != user_id:
        raise HTTPException(status_code=404, detail="Reading list not found")
    return reading_list


@app.post(
    "/users/{user_id}/lists/{list_id}/items",
    response_model=ReadingListItemResponse,
    status_code=201,
    tags=["Reading Lists"],
)
def add_book_to_list(
    user_id: int,
    list_id: int,
    item_data: ReadingListItemCreate,
    db: Session = Depends(get_db),
    auth_user_id: int = Depends(require_auth),
):
    """Add a book to a reading list. Requires authentication as the list owner."""
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only modify your own lists")
    reading_list = services.get_reading_list(db, list_id)
    if reading_list is None or reading_list.user_id != user_id:
        raise HTTPException(status_code=404, detail="Reading list not found")
    book = services.get_book(db, item_data.book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        return services.add_book_to_reading_list(
            db, list_id=list_id, book_id=item_data.book_id, status=item_data.status
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put(
    "/users/{user_id}/lists/{list_id}/items/{item_id}",
    response_model=ReadingListItemResponse,
    tags=["Reading Lists"],
)
def update_list_item_status(
    user_id: int,
    list_id: int,
    item_id: int,
    status: str,
    db: Session = Depends(get_db),
    auth_user_id: int = Depends(require_auth),
):
    """Update the reading status of a book in a list."""
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only modify your own lists")
    reading_list = services.get_reading_list(db, list_id)
    if reading_list is None or reading_list.user_id != user_id:
        raise HTTPException(status_code=404, detail="Reading list not found")
    updated = services.update_reading_list_item_status(db, item_id, status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return updated
