try:
    import pg8000.dbapi as pg8000
except ImportError as import_error:  # Allows the demo UI to run before dependencies are installed.
    pg8000 = None
    PG8000_IMPORT_ERROR = import_error
else:
    PG8000_IMPORT_ERROR = None

from config import DB_CONFIG


class DatabaseUnavailableError(RuntimeError):
    pass


class DictCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.close()

    def execute(self, query, parameters=None):
        self.cursor.execute(query, parameters or ())

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return self._to_dict(row)

    def fetchall(self):
        return [self._to_dict(row) for row in self.cursor.fetchall()]

    def _to_dict(self, row):
        columns = [column[0] for column in self.cursor.description]
        return dict(zip(columns, row))


class DictConnection:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def cursor(self):
        return DictCursor(self.connection.cursor())


def get_connection() -> DictConnection:
    if pg8000 is None:
        raise DatabaseUnavailableError(
            f"pg8000 is not installed. Run: python -m pip install -r requirements.txt. Details: {PG8000_IMPORT_ERROR}"
        )

    if DB_CONFIG["password"] == "MAT_KHAU_POSTGRES":
        raise DatabaseUnavailableError(
            "Set HOTEL_DB_PASSWORD or update config.py with your PostgreSQL password."
        )

    connection = pg8000.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["dbname"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )
    return DictConnection(connection)
