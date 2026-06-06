"""
Business logic layer for the BookClub API.

This module contains all database query logic and business rules.
Route handlers in app.py should delegate to these functions rather
than querying the database directly.
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from bookclub.models import Book, ReadingList, ReadingListItem, Review, User


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

def get_user(db: Session, user_id: int) -> Optional[User]:
    """Get a user by ID."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get a user by username."""
    return db.query(User).filter(User.username == username).first()


def get_users(db: Session) -> list[User]:
    """Get all users."""
    return db.query(User).all()


def create_user(db: Session, username: str, email: str, display_name: str) -> User:
    """Create a new user."""
    user = User(username=username, email=email, display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Book operations
# ---------------------------------------------------------------------------

def get_book(db: Session, book_id: int) -> Optional[Book]:
    """Get a book by ID."""
    return db.query(Book).filter(Book.id == book_id).first()


def get_books(db: Session) -> list[Book]:
    """Get all books."""
    return db.query(Book).all()


def create_book(
    db: Session,
    title: str,
    author: str,
    description: Optional[str] = None,
    published_date: Optional[str] = None,
    isbn: Optional[str] = None,
    page_count: Optional[int] = None,
) -> Book:
    """Create a new book."""
    book = Book(
        title=title,
        author=author,
        description=description,
        published_date=published_date,
        isbn=isbn,
        page_count=page_count,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def update_book(db: Session, book_id: int, **kwargs) -> Optional[Book]:
    """Update a book's fields. Only non-None kwargs are applied."""
    book = get_book(db, book_id)
    if book is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(book, key, value)
    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, book_id: int) -> bool:
    """Delete a book. Returns True if the book existed."""
    book = get_book(db, book_id)
    if book is None:
        return False
    db.delete(book)
    db.commit()
    return True


def search_books(db: Session, query: str) -> list[Book]:
    """Search books by title, author, or description."""
    search_term = f"%{query}%"
    return (
        db.query(Book)
        .filter(
            or_(
                Book.title.ilike(search_term),
                Book.author.ilike(search_term),
                Book.description.ilike(search_term),
            )
        )
        .all()
    )


# ---------------------------------------------------------------------------
# Review operations
# ---------------------------------------------------------------------------

def get_reviews_for_book(db: Session, book_id: int) -> list[Review]:
    """Get all reviews for a book."""
    return db.query(Review).filter(Review.book_id == book_id).all()


def get_review(db: Session, review_id: int) -> Optional[Review]:
    """Get a review by ID."""
    return db.query(Review).filter(Review.id == review_id).first()


def create_review(
    db: Session, user_id: int, book_id: int, rating: int, text: str
) -> Review:
    """
    Create a review for a book.

    Validates:
        - Rating is between 1 and 5
        - Text is not empty
        - User hasn't already reviewed this book
    """
    # Single source of truth for review input validation
    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5")
    if not text or not text.strip():
        raise ValueError("Review text cannot be empty")

    # Check for existing review by this user for this book
    existing = (
        db.query(Review)
        .filter(Review.user_id == user_id, Review.book_id == book_id)
        .first()
    )
    if existing:
        raise ValueError("User has already reviewed this book")

    review = Review(user_id=user_id, book_id=book_id, rating=rating, text=text)
    db.add(review)
    db.commit()
    db.refresh(review)

    # Update book's average rating
    _recalculate_book_rating(db, book_id)

    return review


def _recalculate_book_rating(db: Session, book_id: int):
    """Recalculate and update a book's average rating and count."""
    reviews = get_reviews_for_book(db, book_id)
    book = get_book(db, book_id)
    if book is None:
        return
    if not reviews:
        book.average_rating = 0.0
        book.rating_count = 0
    else:
        book.average_rating = sum(r.rating for r in reviews) / len(reviews)
        book.rating_count = len(reviews)
    db.commit()


# ---------------------------------------------------------------------------
# Reading List operations
# ---------------------------------------------------------------------------

def get_reading_lists_for_user(db: Session, user_id: int) -> list[ReadingList]:
    """Get all reading lists for a user."""
    return db.query(ReadingList).filter(ReadingList.user_id == user_id).all()


def get_reading_list(db: Session, list_id: int) -> Optional[ReadingList]:
    """Get a reading list by ID, including its items."""
    return db.query(ReadingList).filter(ReadingList.id == list_id).first()


def create_reading_list(
    db: Session, user_id: int, name: str, description: Optional[str] = None
) -> ReadingList:
    """Create a new reading list for a user."""
    reading_list = ReadingList(
        user_id=user_id, name=name, description=description
    )
    db.add(reading_list)
    db.commit()
    db.refresh(reading_list)
    return reading_list


def add_book_to_reading_list(
    db: Session, list_id: int, book_id: int, status: str = "unread"
) -> ReadingListItem:
    """Add a book to a reading list."""
    # Check if book is already in the list
    existing = (
        db.query(ReadingListItem)
        .filter(
            ReadingListItem.reading_list_id == list_id,
            ReadingListItem.book_id == book_id,
        )
        .first()
    )
    if existing:
        raise ValueError("Book is already in this reading list")

    item = ReadingListItem(
        reading_list_id=list_id, book_id=book_id, status=status
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_reading_list_item_status(
    db: Session, item_id: int, status: str
) -> Optional[ReadingListItem]:
    """Update the reading status of a book in a reading list."""
    item = db.query(ReadingListItem).filter(ReadingListItem.id == item_id).first()
    if item is None:
        return None
    item.status = status
    db.commit()
    db.refresh(item)
    return item


def remove_book_from_reading_list(db: Session, item_id: int) -> bool:
    """Remove a book from a reading list. Returns True if the item existed."""
    item = db.query(ReadingListItem).filter(ReadingListItem.id == item_id).first()
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True
