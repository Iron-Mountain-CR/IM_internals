import pyodbc
import logging
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, before_sleep_log


# Logger for retry events
logger = logging.getLogger(__name__)


# Retry decorator for SQL operations using Tenacity
sql_retry = retry(
    retry=retry_if_exception(lambda exc: isinstance(exc, pyodbc.Error)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=10),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING)
)


class SqlDatabase:
    """
    A class to manage connections and operations with a SQL database using `pyodbc`.

    The `SqlDatabase` class provides methods for executing SQL queries, calling stored procedures, and retrieving
    metadata such as column positions. It maintains an active database connection and cursor for managing transactions.

    **Attributes**:
        - **sql_connection** (`pyodbc.Connection`): The active SQL database connection.
        - **sql_cursor** (`pyodbc.Cursor`): The cursor for executing SQL queries.

    :param sql_server: The hostname or IP address of the SQL server.
    :type sql_server: str
    :param sql_database: The name of the SQL database.
    :type sql_database: str
    :param sql_user: The username for SQL login.
    :type sql_user: str
    :param sql_password: The password for SQL login.
    :type sql_password: str
    :param sql_port: The port number for the SQL connection.
    :type sql_port: int
    :param sql_driver: The ODBC driver name for SQL connection.
    :type sql_driver: str
    """

    def __init__(self, sql_server: str, sql_database: str, sql_user: str, sql_password: str,
                 sql_port: int, sql_driver=str,):
        """
        Initializes the SQLDatabase class with the given SQL connection details.

        Establishes a connection to the SQL server using the provided details and creates a cursor for executing queries.

        :param sql_server: The hostname or IP address of the SQL server.
        :type sql_server: str
        :param sql_database: The name of the SQL database.
        :type sql_database: str
        :param sql_user: The username for SQL login.
        :type sql_user: str
        :param sql_password: The password for SQL login.
        :type sql_password: str
        :param sql_port: The port number for the SQL connection.
        :type sql_port: int
        :param sql_driver: The ODBC driver name for SQL connection.
        :type sql_driver: str
        """

        self.sql_connection = pyodbc.connect(f'DRIVER={sql_driver};'\
                                             f'SERVER={sql_server};'\
                                             f'DATABASE={sql_database};'\
                                             f'UID={sql_user};'\
                                             f'PWD={sql_password};'\
                                             f'port={sql_port};')
        # self.sql_connection.setdecoding(pyodbc.SQL_CHAR, encoding='Czech_CI_AS')
        # self.sql_connection.setdecoding(pyodbc.SQL_WCHAR, encoding='Czech_CI_AS')
        # self.sql_connection.setencoding(encoding='Czech_CI_AS')
        self.sql_cursor = self.sql_connection.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Closes the SQL connection and logs any exception details if raised.

        This method is automatically called upon exit, ensuring the connection is closed properly. If any exceptions
        occur during the class's usage, they are logged using the `logging` module.

        :param exc_type: Type of the exception.
        :type exc_type: Exception
        :param exc_val: Value of the exception.
        :type exc_val: Exception
        :param exc_tb: Traceback details of the exception.
        :type exc_tb: traceback
        """

        logger = logging.getLogger("SQL_CLASS_ERROR")
        self.sql_connection.close()

        if exc_type is not None and exc_val is not None and exc_tb is not None:
            logger.error(f"Exception Type: {exc_type}")
            logger.error(f"Exception Value: {exc_val}")
            logger.error(f"Exception Traceback: {exc_tb}")

    @property
    def connection(self):
        """
        Retrieves the active SQL connection.

        :return: The active SQL connection object.
        :rtype: pyodbc.Connection
        """

        return self.sql_connection

    @property
    def cursor(self):
        """
        Retrieves the SQL cursor for executing queries.

        :return: The SQL cursor object.
        :rtype: pyodbc.Cursor
        """

        return self.sql_cursor

    def commit(self):
        """
        Commits the current transaction to the SQL database.

        This method ensures that all changes made by the previous queries are saved in the database.
        """

        self.connection.commit()

    def execute(self, sql, params=None):
        """
        Executes a SQL query with optional parameters.

        :param sql: The SQL query to execute.
        :type sql: str
        :param params: Optional, a tuple of parameters to bind to the SQL query.
        :type params: tuple, optional
        """

        self.cursor.execute(sql, params or ())

    def fetchall(self):
        """
        Fetches all rows from the executed query.

        :return: A list of rows from the query result.
        :rtype: list
        """

        return self.cursor.fetchall()

    def fetchone(self):
        """
        Fetches the first row from the executed query.

        :return: The first row from the query result.
        :rtype: Any
        """

        return self.cursor.fetchone()

    @sql_retry
    def query(self, sql, params=None):
        """
        Executes a SQL query and fetches all rows from the result.

        :param sql: The SQL query to execute.
        :type sql: str
        :param params: Optional, a tuple of parameters to bind to the SQL query.
        :type params: tuple, optional
        :return: A list of rows from the query result.
        :rtype: list
        """

        self.cursor.execute(sql, params or ())
        return self.fetchall()

    @sql_retry
    def rollback(self):
        """
        Rollback any pending transaction
        """
        self.connection.rollback()

    @staticmethod
    @sql_retry
    def call_sql_procedure(sql_connection_text: str, procedure_name: str, **kvargs):
        """
        Calls a SQL stored procedure with specified parameters.

        This method executes a stored procedure on the SQL server using the provided connection string and parameters.

        :param sql_connection_text: The SQL connection string.
        :type sql_connection_text: str
        :param procedure_name: The name of the stored procedure to call.
        :type procedure_name: str
        :param kvargs: Keyword arguments representing the parameters required by the procedure.
        :return: The results of the stored procedure in a list of tuples.
        :rtype: list
        """

        count = 0
        sql_variables = ""

        for kvarg in kvargs:
            if len(kvargs) == 1:
                sql_variables = f"@{kvarg}={kvargs[kvarg]}"
            elif len(kvargs) > 1:
                if count == (len(kvargs) - 1):
                    sql_variables += f"@{kvarg}={kvargs[kvarg]}"
                else:
                    sql_variables += f"@{kvarg}={kvargs[kvarg]}, "
                count += 1

        with pyodbc.connect(sql_connection_text) as sql_connection:
            sql_cursor = sql_connection.cursor()
            sql_query = f"EXEC {procedure_name} {sql_variables}"
            sql_cursor.execute(sql_query)
            results = sql_cursor.fetchall()

        return results

    @sql_retry
    def column_names(self, table: str, columns: list | str):
        """
        Retrieves the positions of specified columns in a given table.

        :param table: The name of the table to retrieve column positions from.
        :type table: str
        :param columns: A single column name or a list of column names to look for.
        :type columns: list | str
        :return: A dictionary with column names as keys and their positions as values.
        :rtype: dict
        :raises ValueError: If `columns` is not a string or a list.
        """

        column_positions = {}

        for column_info in self.sql_cursor.columns(table=table):
            if type(columns) is list:
                if len(columns) > 1:
                    for column in columns:
                        if column_info.column_name == columns:
                            column_positions[column] = column_info.ordinal_position - 1
                else:
                    if column_info.column_name == columns[0]:
                        column_positions[columns[0]] = column_info.ordinal_position - 1
            elif type(columns) is str:
                if column_info.column_name == columns:
                    column_positions[columns] = column_info.ordinal_position - 1
            else:
                raise ValueError(f"Expected List or String information, but got {type(columns)}")

        return column_positions
