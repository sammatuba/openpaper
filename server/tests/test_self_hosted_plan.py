"""SELF_HOSTED_PLAN replaces the Stripe subscription lookup on a personal
instance; unset leaves upstream's behaviour."""

import os
import unittest
from unittest import mock

from app.database.models import SubscriptionPlan
from app.helpers import subscription_limits


class SelfHostedPlan(unittest.TestCase):
    def test_forced_plan_skips_the_subscription_lookup(self):
        with mock.patch.dict(os.environ, {"SELF_HOSTED_PLAN": "researcher"}):
            with mock.patch.object(subscription_limits.subscription_crud, "get_by_user_id") as lookup:
                plan = subscription_limits.get_user_subscription_plan(mock.Mock(), mock.Mock())
        self.assertEqual(plan, SubscriptionPlan.RESEARCHER)
        lookup.assert_not_called()

    def test_unset_uses_the_subscription(self):
        with mock.patch.dict(os.environ, {"SELF_HOSTED_PLAN": ""}):
            with mock.patch.object(
                subscription_limits.subscription_crud, "get_by_user_id", return_value=None
            ) as lookup:
                plan = subscription_limits.get_user_subscription_plan(mock.Mock(), mock.Mock())
        self.assertEqual(plan, SubscriptionPlan.BASIC)
        lookup.assert_called_once()

    def test_unknown_value_is_ignored(self):
        with mock.patch.dict(os.environ, {"SELF_HOSTED_PLAN": "platinum"}):
            with mock.patch.object(
                subscription_limits.subscription_crud, "get_by_user_id", return_value=None
            ):
                plan = subscription_limits.get_user_subscription_plan(mock.Mock(), mock.Mock())
        self.assertEqual(plan, SubscriptionPlan.BASIC)


if __name__ == "__main__":
    unittest.main()
