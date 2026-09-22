"""
Turns the data dictionary + the actual distinct values in the dataset into
lookup tables the parser can use to recognise what a query is talking
about. Keeping this separate from the parser means that if the dictionary
changes, or the dataset grows to include new regions/categories, nothing
in the parsing logic itself needs to change.
"""

MONTH_NAMES = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


class Schema:
    def __init__(self, data_dictionary, conn):
        self.dictionary = data_dictionary
        self.metrics = data_dictionary.get("metrics", {})
        self.dimensions = data_dictionary.get("dimensions", [])
        self.synonyms = {k.lower(): v for k, v in data_dictionary.get("synonyms", {}).items()}

        cur = conn.cursor()
        self.regions = self._distinct(cur, "region")
        self.countries = self._distinct(cur, "country")
        self.cities = self._distinct(cur, "city")
        self.segments = self._distinct(cur, "customer_segment")
        self.categories = self._distinct(cur, "product_category")
        self.subcategories = self._distinct(cur, "product_subcategory")
        self.products = self._distinct(cur, "product_name")
        self.years = self._distinct(cur, "year", table="sales_v")

        # dimension -> known values, used to spot which value in the query
        # text belongs to which column
        self.dimension_values = {
            "region": self.regions,
            "country": self.countries,
            "city": self.cities,
            "customer_segment": self.segments,
            "product_category": self.categories,
            "product_subcategory": self.subcategories,
            "product_name": self.products,
        }

        # a handful of extra phrases people use for the same dimension
        self.dimension_aliases = {
            "region": ["region"],
            "country": ["country"],
            "city": ["city"],
            "customer_segment": ["segment", "customer segment", "customer type"],
            "product_category": ["category"],
            "product_subcategory": ["subcategory", "sub category", "sub-category"],
            "customer_id": ["customer", "customers", "client"],
            "product_name": ["product", "products"],
        }

    @staticmethod
    def _distinct(cur, column, table="sales"):
        cur.execute(f"SELECT DISTINCT {column} FROM {table}")
        return sorted(str(r[0]) for r in cur.fetchall())

    def resolve_metric(self, word):
        """Maps a word from the query onto one of the metrics defined in
        the data dictionary, following the synonyms table first."""
        word = word.lower()
        if word in self.synonyms:
            target = self.synonyms[word]
            # synonyms sometimes point straight at an expression, e.g.
            # "orders" -> "count(order_id)" - normalise those back to a
            # metric name we already know about
            if target in self.metrics:
                return target
            for name, expr in self.metrics.items():
                if expr.replace(" ", "") == target.replace(" ", ""):
                    return name
            return target
        if word in self.metrics:
            return word
        return None
