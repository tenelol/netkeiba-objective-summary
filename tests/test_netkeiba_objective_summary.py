from __future__ import annotations

import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import netkeiba_objective_summary as target  # noqa: E402


class NetkeibaObjectiveSummaryTests(unittest.TestCase):
    def test_extract_comment_list_config_from_horse_board_html(self) -> None:
        html = """
        <script>
        var _bbs_action_api_url = 'https://bbs.netkeiba.com/';
        showCommentList( 'Comment_List', 1, '2022105076',
          'https://db.netkeiba.com/?pid=horse_board&id=2022105076',
          'Comment_Form', 1000, 'スクレイピング',
          'https://db.netkeiba.com/?pid=horse_board&id=2022105076',
          'p', 'https://db.netkeiba.com/?pid=horse_board&id=2022105076',
          'refresh_comment_list_2',
          'https://db.netkeiba.com/?pid=horse_bbs_report&id=2022105076',
          20, 1,
          'https://db.netkeiba.com/?pid=horse_like_comment_list&id=2022105076',
          'horse' );
        </script>
        """

        config = target.extract_comment_list_config(html)

        self.assertEqual(config.api_url, "https://bbs.netkeiba.com/")
        self.assertEqual(config.params["pid"], "api_get_comment_list")
        self.assertEqual(config.params["output"], "json")
        self.assertEqual(config.params["sort"], "1")
        self.assertEqual(config.params["key"], "2022105076")
        self.assertEqual(config.params["category_cd"], "horse")

    def test_comments_from_api_payload_strips_html_and_hidden_comments(self) -> None:
        payload = {
            "status": "OK",
            "data": {
                "list": [
                    {
                        "comment_id": "211",
                        "comment": "東京コースで<br>出走予定",
                        "datetime": "2026/2/21 21:39",
                        "like_count": "3",
                        "is_hidden_comment": "0",
                    },
                    {
                        "comment_id": "212",
                        "comment": "hidden",
                        "is_hidden_comment": "1",
                    },
                ]
            },
        }

        comments = target.comments_from_api_payload(payload)

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].comment_id, "211")
        self.assertEqual(comments[0].like_count, 3)
        self.assertIn("東京コース", comments[0].text)
        self.assertIn("出走予定", comments[0].text)

    def test_prepare_model_comments_respects_character_limit(self) -> None:
        comments = [
            target.BoardComment(str(i), "", "x" * 100, 0)
            for i in range(10)
        ]

        prepared, serialized_size = target.prepare_model_comments(
            comments,
            max_comments=10,
            max_input_chars=500,
        )

        self.assertLessEqual(serialized_size, 500)
        self.assertLess(len(prepared), 10)

    def test_extract_json_object_from_fenced_output(self) -> None:
        data = target.extract_json_object(
            "```json\n"
            + json.dumps({"objective_summary": []})
            + "\n```"
        )

        self.assertEqual(data["objective_summary"], [])


if __name__ == "__main__":
    unittest.main()
