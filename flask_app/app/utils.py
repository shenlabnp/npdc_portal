def construct_numeric_filter(search_term, db_column):
    """
    Constructs a SQL filter for GC content based on the search term.
    Parameters:
    - search_term: The search term entered by the user.
    - db_column: The database column to apply the filter to.
    Returns:
    - A tuple containing the SQL filter string and a list of parameters.
    """
    try:
        # Check for range input min-max
        if '-' in search_term:
            lower_bound, upper_bound = map(float, search_term.split('-', 1))
            sql_filter = f" and {db_column} BETWEEN ? AND ?"
            params = [lower_bound, upper_bound]
        # Check for greater than ">"
        elif search_term.startswith('>'):
            lower_bound = float(search_term[1:])
            sql_filter = f" and {db_column} > ?"
            params = [lower_bound]
        # Check for less than "<"
        elif search_term.startswith('<'):
            upper_bound = float(search_term[1:])
            sql_filter = f" and {db_column} < ?"
            params = [upper_bound]
        else:
            # Assume range match if no operator is used
            term_as_float = float(search_term)
            lower_bound = term_as_float - 0.5
            lower_bound = max(lower_bound, 0)
            upper_bound = term_as_float + 0.5
            sql_filter = f" and {db_column} BETWEEN ? AND ?"
            params = [lower_bound, upper_bound]

    except ValueError:
        # Handle the case where the term is not a valid range or number
        sql_filter = ""
        params = []

    return sql_filter, params