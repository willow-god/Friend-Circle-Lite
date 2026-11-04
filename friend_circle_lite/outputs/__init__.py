"""Output assembly: JSON I/O, article processing, and remote merging."""

from friend_circle_lite.outputs.json_io import read_json, write_json
from friend_circle_lite.outputs.merge import merge_article_data, merge_error_data, merge_link_data
from friend_circle_lite.outputs.processing import finalize_article_data, sort_articles_by_time

__all__ = [
    "finalize_article_data",
    "merge_article_data",
    "merge_error_data",
    "merge_link_data",
    "read_json",
    "sort_articles_by_time",
    "write_json",
]
