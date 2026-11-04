import unittest
from pathlib import Path


class WorkflowTest(unittest.TestCase):
    def test_ci_workflow_runs_lint_and_tests(self):
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("pull_request:", workflow)
        self.assertIn("workflow_call:", workflow)
        self.assertIn("pip install -r requirements-dev.txt", workflow)
        self.assertIn("ruff check .", workflow)
        self.assertIn("python -m pytest", workflow)
        self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true", workflow)

    def test_scheduled_workflow_is_gated_by_quality_checks(self):
        workflow = Path(".github/workflows/friend_circle_lite.yml").read_text(encoding="utf-8")

        self.assertIn("quality-checks:", workflow)
        self.assertIn("uses: ./.github/workflows/ci.yml", workflow)
        self.assertIn("needs: quality-checks", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("timeout-minutes: 30", workflow)

    def test_github_action_schedule_uses_22_minute_offset(self):
        workflow = Path(".github/workflows/friend_circle_lite.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "22 */4 * * *"', workflow)
        self.assertNotIn('cron: "0 */4 * * *"', workflow)

    def test_github_actions_opt_into_node24_runtime(self):
        workflow_paths = [
            Path(".github/workflows/friend_circle_lite.yml"),
            Path(".github/workflows/deal_subscribe_issue.yml"),
            Path(".github/workflows/ci.yml"),
        ]

        for workflow_path in workflow_paths:
            with self.subTest(workflow=str(workflow_path)):
                workflow = workflow_path.read_text(encoding="utf-8")
                self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true", workflow)

    def test_publish_workflow_skips_unchanged_page_tree(self):
        workflow = Path(".github/workflows/friend_circle_lite.yml").read_text(encoding="utf-8")

        self.assertIn('git fetch origin "${PAGE_BRANCH}:refs/remotes/origin/${PAGE_BRANCH}"', workflow)
        self.assertIn('published_tree=$(git rev-parse "origin/${PAGE_BRANCH}^{tree}")', workflow)
        self.assertIn("generated_tree=$(git write-tree)", workflow)
        self.assertIn('[ "$generated_tree" = "$published_tree" ]', workflow)
        self.assertIn("No static asset changes; skipping page branch update.", workflow)


if __name__ == "__main__":
    unittest.main()
