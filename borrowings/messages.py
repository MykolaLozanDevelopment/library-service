def build_borrowing_message(borrowing):
    return (
        f"📚 New borrowing #{borrowing.id}\n"
        f"User: {borrowing.user.email}\n"
        f"Book: {borrowing.book.title} by {borrowing.book.author}\n"
        f"Borrowed: {borrowing.borrow_date}\n"
        f"Expected return: {borrowing.expected_return_date}"
    )
