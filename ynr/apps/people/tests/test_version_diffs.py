import re

from django.test import TestCase

import people.tests.factories
from candidates.diffs import get_version_diff, get_version_diffs
from candidates.tests.uk_examples import UK2015ExamplesMixin


def sort_operations_for_comparison(versions_with_diffs):
    for v in versions_with_diffs:
        v["diffs"].sort(key=lambda pd: pd["parent_version_id"])
        for parent_data in v["diffs"]:
            parent_data["parent_diff"].sort(key=lambda o: (o["op"], o["path"]))


def tidy_html_whitespace(html):
    tidied = re.sub(r"(?ms)>\s+<", "><", html.strip())
    return re.sub(r"(?ms)\s+", " ", tidied)


class TestVersionDiffs(UK2015ExamplesMixin, TestCase):

    maxDiff = None

    def setUp(self):
        super().setUp()

    def test_get_version_diffs(self):
        versions = [
            {
                "user": "john",
                "information_source": "Manual correction by a user",
                "timestamp": "2015-06-10T05:35:15.297559",
                "version_id": "8aa71db8f2f20bf8",
                "data": {
                    "id": "24680",
                    "a": "alpha",
                    "b": "beta",
                    "g": "",
                    "h": None,
                    "l": "lambda",
                },
            },
            {
                "information_source": "Updated by a script",
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "643dc3343880f168",
                "data": {
                    "id": "24680",
                    "a": "alpha",
                    "b": "LATIN SMALL LETTER B",
                    "d": "delta",
                    "g": None,
                    "h": "",
                    "l": "lambda",
                },
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-07T05:35:15.297559",
                "version_id": "42648e36ff699179",
                "data": {"id": "24680", "a": "alpha", "b": "beta", "l": None},
            },
        ]

        expected_result = [
            {
                "user": "john",
                "information_source": "Manual correction by a user",
                "timestamp": "2015-06-10T05:35:15.297559",
                "version_id": "8aa71db8f2f20bf8",
                "parent_version_ids": ["643dc3343880f168"],
                "data": {
                    "id": "24680",
                    "a": "alpha",
                    "b": "beta",
                    "g": "",
                    "h": None,
                    "l": "lambda",
                },
                "diffs": [
                    {
                        "parent_version_id": "643dc3343880f168",
                        "parent_diff": [
                            {
                                "op": "remove",
                                "path": "d",
                                "previous_value": "delta",
                            },
                            {
                                "op": "replace",
                                "path": "b",
                                "previous_value": "LATIN SMALL LETTER B",
                                "value": "beta",
                            },
                        ],
                    }
                ],
            },
            {
                "information_source": "Updated by a script",
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "643dc3343880f168",
                "parent_version_ids": ["42648e36ff699179"],
                "data": {
                    "id": "24680",
                    "a": "alpha",
                    "b": "LATIN SMALL LETTER B",
                    "d": "delta",
                    "g": None,
                    "h": "",
                    "l": "lambda",
                },
                "diffs": [
                    {
                        "parent_version_id": "42648e36ff699179",
                        "parent_diff": [
                            {"op": "add", "path": "d", "value": "delta"},
                            {
                                "op": "add",
                                "path": "l",
                                "previous_value": None,
                                "value": "lambda",
                            },
                            {
                                "op": "replace",
                                "path": "b",
                                "previous_value": "beta",
                                "value": "LATIN SMALL LETTER B",
                            },
                        ],
                    }
                ],
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-07T05:35:15.297559",
                "version_id": "42648e36ff699179",
                "parent_version_ids": [],
                "data": {"id": "24680", "a": "alpha", "b": "beta", "l": None},
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {"op": "add", "path": "a", "value": "alpha"},
                            {"op": "add", "path": "b", "value": "beta"},
                            {"op": "add", "path": "id", "value": "24680"},
                        ],
                    }
                ],
            },
        ]

        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)

        self.assertEqual(expected_result, versions_with_diffs)

    def test_versions_2010_then_adding_2015(self):
        versions = [
            {
                "information_source": 'After clicking "Standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "3aa8d7da968e10fa",
                "data": {
                    "id": "24680",
                    "candidacies": {
                        "parl.65922.2010-05-06": {"party": "PP58"},
                        "parl.14420.2015-05-07": {"party": "PP85"},
                    },
                },
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "fd105d1cf3b5ed0f",
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65922.2010-05-06": {"party": "PP58"}},
                },
            },
        ]

        expected_result = [
            {
                "information_source": 'After clicking "Standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "3aa8d7da968e10fa",
                "parent_version_ids": ["fd105d1cf3b5ed0f"],
                "data": {
                    "id": "24680",
                    "candidacies": {
                        "parl.65922.2010-05-06": {"party": "PP58"},
                        "parl.14420.2015-05-07": {"party": "PP85"},
                    },
                },
                "diffs": [
                    {
                        "parent_version_id": "fd105d1cf3b5ed0f",
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "candidacies/parl.14420.2015-05-07",
                                "value": "stood for PP85",
                            }
                        ],
                    }
                ],
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "fd105d1cf3b5ed0f",
                "parent_version_ids": [],
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65922.2010-05-06": {"party": "PP58"}},
                },
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "candidacies",
                                "value": {
                                    "parl.65922.2010-05-06": {"party": "PP58"}
                                },
                            },
                            {"op": "add", "path": "id", "value": "24680"},
                        ],
                    }
                ],
            },
        ]

        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)

        self.assertEqual(expected_result, versions_with_diffs)

    def test_versions_2010_then_definitely_not_2015(self):
        versions = [
            {
                "information_source": 'After clicking "Not standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "698ae05960970b60",
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65922.2010-05-06": {"party": "PP58"}},
                    "not_standing": ["parl.2015-05-07"],
                },
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "d1fd9c3830d8d722",
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65922.2010-05-06": {"party": "PP58"}},
                },
            },
        ]

        expected_result = [
            {
                "information_source": 'After clicking "Not standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "698ae05960970b60",
                "parent_version_ids": ["d1fd9c3830d8d722"],
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65922.2010-05-06": {"party": "PP58"}},
                    "not_standing": ["parl.2015-05-07"],
                },
                "diffs": [
                    {
                        "parent_version_id": "d1fd9c3830d8d722",
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "not_standing",
                                "value": ["parl.2015-05-07"],
                            }
                        ],
                    }
                ],
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "d1fd9c3830d8d722",
                "parent_version_ids": [],
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65922.2010-05-06": {"party": "PP58"}},
                },
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "candidacies",
                                "value": {
                                    "parl.65922.2010-05-06": {"party": "PP58"}
                                },
                            },
                            {"op": "add", "path": "id", "value": "24680"},
                        ],
                    }
                ],
            },
        ]

        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)

        self.assertEqual(expected_result, versions_with_diffs)

    def test_versions_just_party_changed(self):
        versions = [
            {
                "information_source": 'After clicking "Not standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "95ac9c97c1d72ebb",
                "data": {
                    "id": "24680",
                    "candidacies": {
                        "parl.stroud.2010-05-06": {"party": "party:58"},
                        "parl.stroud.2015-05-07": {"party": "ynmp-party:2"},
                    },
                },
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "10fcaee60b9f5203",
                "data": {
                    "id": "24680",
                    "candidacies": {
                        "parl.stroud.2010-05-06": {"party": "party:58"},
                        "parl.stroud.2015-05-07": {"party": "party:58"},
                    },
                },
            },
        ]

        expected_result = [
            {
                "information_source": 'After clicking "Not standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "95ac9c97c1d72ebb",
                "parent_version_ids": ["10fcaee60b9f5203"],
                "data": {
                    "id": "24680",
                    "candidacies": {
                        "parl.stroud.2010-05-06": {"party": "party:58"},
                        "parl.stroud.2015-05-07": {"party": "ynmp-party:2"},
                    },
                },
                "diffs": [
                    {
                        "parent_version_id": "10fcaee60b9f5203",
                        "parent_diff": [
                            {
                                "op": "replace",
                                "path": "candidacies/parl.stroud.2015-05-07/party",
                                "previous_value": "party:58",
                                "value": "ynmp-party:2",
                            }
                        ],
                    }
                ],
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "10fcaee60b9f5203",
                "parent_version_ids": [],
                "data": {
                    "id": "24680",
                    "candidacies": {
                        "parl.stroud.2010-05-06": {"party": "party:58"},
                        "parl.stroud.2015-05-07": {"party": "party:58"},
                    },
                },
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "candidacies",
                                "value": {
                                    "parl.stroud.2010-05-06": {
                                        "party": "party:58"
                                    },
                                    "parl.stroud.2015-05-07": {
                                        "party": "party:58"
                                    },
                                },
                            },
                            {"op": "add", "path": "id", "value": "24680"},
                        ],
                    }
                ],
            },
        ]

        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)

        self.assertEqual(expected_result, versions_with_diffs)

    def test_versions_just_constituency_changed(self):
        versions = [
            {
                "information_source": 'After clicking "Not standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "65c16b93a0f41b00",
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65659.2015-05-07": {"party": "PP58"}},
                },
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "1a5144605b4c1498",
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65808.2015-05-07": {"party": "PP58"}},
                },
            },
        ]

        expected_result = [
            {
                "information_source": 'After clicking "Not standing again"',
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "65c16b93a0f41b00",
                "parent_version_ids": ["1a5144605b4c1498"],
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65659.2015-05-07": {"party": "PP58"}},
                },
                "diffs": [
                    {
                        "parent_version_id": "1a5144605b4c1498",
                        "parent_diff": [
                            {
                                "op": "move",
                                "path": "candidacies/parl.65659.2015-05-07",
                                "from": "/candidacies/parl.65808.2015-05-07",
                            }
                        ],
                    }
                ],
            },
            {
                "information_source": "Original imported data",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "1a5144605b4c1498",
                "parent_version_ids": [],
                "data": {
                    "id": "24680",
                    "candidacies": {"parl.65808.2015-05-07": {"party": "PP58"}},
                },
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "candidacies",
                                "value": {
                                    "parl.65808.2015-05-07": {"party": "PP58"}
                                },
                            },
                            {"op": "add", "path": "id", "value": "24680"},
                        ],
                    }
                ],
            },
        ]
        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)

        self.assertEqual(expected_result, versions_with_diffs)

    def test_remove_ids_for_version_diffs(self):
        versions = [
            {
                "user": "john",
                "information_source": "Manual correction by a user",
                "timestamp": "2015-04-12T05:35:15.297559",
                "version_id": "e6dcd55bb903499e",
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "note": "Full name",
                            "start_date": None,
                            "id": "567890",
                            "end_date": None,
                            "name": "Tessa Jane Jowell",
                        }
                    ],
                },
            },
            {
                "information_source": "Updated by a script",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "788a3291f1103de5",
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "note": "Full name",
                            "start_date": None,
                            "id": "567891",
                            "end_date": None,
                            "name": "Tessa J Jowell",
                        }
                    ],
                },
            },
        ]

        expected_result = [
            {
                "user": "john",
                "information_source": "Manual correction by a user",
                "timestamp": "2015-04-12T05:35:15.297559",
                "version_id": "e6dcd55bb903499e",
                "parent_version_ids": ["788a3291f1103de5"],
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "note": "Full name",
                            "start_date": None,
                            "end_date": None,
                            "name": "Tessa Jane Jowell",
                        }
                    ],
                },
                "diffs": [
                    {
                        "parent_version_id": "788a3291f1103de5",
                        "parent_diff": [
                            {
                                "path": "other_names/0/name",
                                "previous_value": "Tessa J Jowell",
                                "value": "Tessa Jane Jowell",
                                "op": "replace",
                            }
                        ],
                    }
                ],
            },
            {
                "information_source": "Updated by a script",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "788a3291f1103de5",
                "parent_version_ids": [],
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "note": "Full name",
                            "start_date": None,
                            "end_date": None,
                            "name": "Tessa J Jowell",
                        }
                    ],
                },
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {"op": "add", "path": "id", "value": "24680"},
                            {
                                "op": "add",
                                "path": "other_names",
                                "value": [
                                    {
                                        "end_date": None,
                                        "name": "Tessa J Jowell",
                                        "note": "Full name",
                                        "start_date": None,
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
        ]

        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)

        self.assertEqual(expected_result, versions_with_diffs)

    def test_index_error(self):
        versions = [
            {
                "user": "john",
                "information_source": "Manual correction by a user",
                "timestamp": "2015-04-12T05:35:15.297559",
                "version_id": "a2fd462d7b9ea219",
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "end_date": "",
                            "name": "Joey",
                            "note": "",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Joseph Tribbiani",
                            "note": "",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Jonathan Francis Tribbiani",
                            "note": "Ballot paper",
                            "start_date": "",
                        },
                    ],
                },
            },
            {
                "information_source": "Updated by a script",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "66b78855c5f19197",
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "end_date": "",
                            "name": "Joseph Tribbiani",
                            "note": "",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Jonathan Francis Tribbiani",
                            "note": "Ballot paper",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Joey",
                            "note": "",
                            "start_date": "",
                        },
                    ],
                },
            },
        ]

        expected_result = [
            {
                "user": "john",
                "information_source": "Manual correction by a user",
                "timestamp": "2015-04-12T05:35:15.297559",
                "version_id": "a2fd462d7b9ea219",
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "end_date": "",
                            "name": "Joey",
                            "note": "",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Joseph Tribbiani",
                            "note": "",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Jonathan Francis Tribbiani",
                            "note": "Ballot paper",
                            "start_date": "",
                        },
                    ],
                },
                "parent_version_ids": ["66b78855c5f19197"],
                "diffs": [
                    {
                        "parent_version_id": "66b78855c5f19197",
                        "parent_diff": [
                            {
                                "op": "add",
                                "path": "other_names/2/note",
                                "value": "Ballot paper",
                                "previous_value": "",
                            },
                            {
                                "op": "replace",
                                "path": "other_names/0/name",
                                "value": "Joey",
                                "previous_value": "Joseph Tribbiani",
                            },
                            {
                                "op": "replace",
                                "path": "other_names/1/name",
                                "value": "Joseph Tribbiani",
                                "previous_value": "Jonathan Francis Tribbiani",
                            },
                            {
                                "op": "replace",
                                "path": "other_names/1/note",
                                "value": "",
                                "previous_value": "Ballot paper",
                            },
                            {
                                "op": "replace",
                                "path": "other_names/2/name",
                                "value": "Jonathan Francis Tribbiani",
                                "previous_value": "Joey",
                            },
                        ],
                    }
                ],
            },
            {
                "information_source": "Updated by a script",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "66b78855c5f19197",
                "data": {
                    "id": "24680",
                    "identifiers": [],
                    "other_names": [
                        {
                            "end_date": "",
                            "name": "Joseph Tribbiani",
                            "note": "",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Jonathan Francis Tribbiani",
                            "note": "Ballot paper",
                            "start_date": "",
                        },
                        {
                            "end_date": "",
                            "name": "Joey",
                            "note": "",
                            "start_date": "",
                        },
                    ],
                },
                "parent_version_ids": [],
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {"op": "add", "path": "id", "value": "24680"},
                            {
                                "op": "add",
                                "path": "other_names",
                                "value": [
                                    {
                                        "end_date": "",
                                        "name": "Joseph Tribbiani",
                                        "note": "",
                                        "start_date": "",
                                    },
                                    {
                                        "end_date": "",
                                        "name": "Jonathan Francis Tribbiani",
                                        "note": "Ballot paper",
                                        "start_date": "",
                                    },
                                    {
                                        "end_date": "",
                                        "name": "Joey",
                                        "note": "",
                                        "start_date": "",
                                    },
                                ],
                            },
                        ],
                    }
                ],
            },
        ]

        # This shouldn't raise an exception, but does at the moment:
        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)
        self.assertEqual(expected_result, versions_with_diffs)

    def test_alternative_names(self):
        versions = [
            {
                "data": {
                    "honorific_prefix": "Mrs",
                    "honorific_suffix": "",
                    "id": "6704",
                    "identifiers": [],
                    "image": None,
                    "linkedin_url": "",
                    "name": "Sarah Jones",
                    "other_names": [
                        {
                            "id": "552f80d0ed1c6ee164eeae50",
                            "name": "Sarah Smith",
                            "note": "Maiden name",
                        }
                    ],
                    "party_ppc_page_url": "",
                    "proxy_image": None,
                    "twitter_username": "",
                    "wikipedia_url": "",
                },
                "information_source": "Made up 2",
                "timestamp": "2015-05-08T01:52:27.061038",
                "username": "test",
                "version_id": "3fc494d54f61a157",
            },
            {
                "data": {
                    "honorific_prefix": "Mrs",
                    "honorific_suffix": "",
                    "id": "6704",
                    "identifiers": [],
                    "image": None,
                    "linkedin_url": "",
                    "name": "Sarah Jones",
                    "other_names": [{"name": "Sarah Smith"}],
                    "party_ppc_page_url": "",
                    "proxy_image": None,
                    "twitter_username": "",
                    "wikipedia_url": "",
                },
                "information_source": "Made up 1",
                "timestamp": "2015-03-10T05:35:15.297559",
                "username": "test",
                "version_id": "2f07734529a83242",
            },
        ]

        versions_with_diffs = get_version_diffs(versions)
        sort_operations_for_comparison(versions_with_diffs)
        expected_result = [
            {
                "information_source": "Made up 2",
                "username": "test",
                "timestamp": "2015-05-08T01:52:27.061038",
                "version_id": "3fc494d54f61a157",
                "parent_version_ids": ["2f07734529a83242"],
                "diffs": [
                    {
                        "parent_version_id": "2f07734529a83242",
                        "parent_diff": [
                            {
                                "path": "other_names/0/note",
                                "value": "Maiden name",
                                "op": "add",
                            }
                        ],
                    }
                ],
                "data": {
                    "honorific_suffix": "",
                    "party_ppc_page_url": "",
                    "linkedin_url": "",
                    "image": None,
                    "twitter_username": "",
                    "id": "6704",
                    "name": "Sarah Jones",
                    "identifiers": [],
                    "other_names": [
                        {"note": "Maiden name", "name": "Sarah Smith"}
                    ],
                    "honorific_prefix": "Mrs",
                    "wikipedia_url": "",
                },
            },
            {
                "information_source": "Made up 1",
                "username": "test",
                "timestamp": "2015-03-10T05:35:15.297559",
                "version_id": "2f07734529a83242",
                "parent_version_ids": [],
                "diffs": [
                    {
                        "parent_version_id": None,
                        "parent_diff": [
                            {
                                "path": "honorific_prefix",
                                "value": "Mrs",
                                "op": "add",
                            },
                            {"path": "id", "value": "6704", "op": "add"},
                            {
                                "path": "name",
                                "value": "Sarah Jones",
                                "op": "add",
                            },
                            {
                                "path": "other_names",
                                "value": [{"name": "Sarah Smith"}],
                                "op": "add",
                            },
                        ],
                    }
                ],
                "data": {
                    "honorific_suffix": "",
                    "party_ppc_page_url": "",
                    "linkedin_url": "",
                    "image": None,
                    "twitter_username": "",
                    "id": "6704",
                    "name": "Sarah Jones",
                    "identifiers": [],
                    "other_names": [{"name": "Sarah Smith"}],
                    "honorific_prefix": "Mrs",
                    "wikipedia_url": "",
                },
            },
        ]
        self.assertEqual(expected_result, versions_with_diffs)

    def test_broken_diff(self):
        """
        Due to a bug in JsonPatch (https://github.com/stefankoegl/python-json-patch/issues/91)
        a list with duplicate dicts in will raise an exception.

        This is a regression test to make sure that we're dealing with
        it ourselves.
        """

        from_v = {"foo": [{"baz": 2}, {"bar": 1}, {"bar": 1}]}
        to_v = {"foo": [{"baz": 2}]}
        diff = get_version_diff(from_v, to_v)
        self.assertEqual(
            diff,
            [
                {"op": "remove", "path": "foo/1", "previous_value": {"bar": 1}},
                {"op": "remove", "path": "foo/1", "previous_value": {"bar": 1}},
            ],
        )


class TestSingleVersionRendering(UK2015ExamplesMixin, TestCase):

    maxDiff = None

    def setUp(self):
        super().setUp()
        self.example_person = people.tests.factories.PersonFactory.create(
            name="Sarah Jones",
            versions="""[{
                "data": {
                    "honorific_prefix": "Mrs",
                    "honorific_suffix": "",
                    "id": "6704",
                    "identifiers": [],
                    "image": null,
                    "linkedin_url": "",
                    "name": "Sarah Jones",
                    "other_names": [{
                        "id": "552f80d0ed1c6ee164eeae50",
                        "name": "Sarah Smith",
                        "note": "Maiden name"
                    }],
                    "party_ppc_page_url": "",
                    "proxy_image": null,
                    "twitter_username": "",
                    "wikipedia_url": ""
                },
                "information_source": "Made up 2",
                "timestamp": "2015-05-08T01:52:27.061038",
                "username": "test",
                "version_id": "3fc494d54f61a157"
            },
            {
                "data": {
                    "honorific_prefix": "Mrs",
                    "honorific_suffix": "",
                    "id": "6704",
                    "identifiers": [],
                    "image": null,
                    "linkedin_url": "",
                    "name": "Sarah Jones",
                    "other_names": [
                        {"name": "Sarah Smith"}
                    ],
                    "party_ppc_page_url": "",
                    "proxy_image": null,
                    "twitter_username": "",
                    "wikipedia_url": ""
                },
                "information_source": "Made up 1",
                "timestamp": "2015-03-10T05:35:15.297559",
                "username": "test",
                "version_id": "2f07734529a83242"
            }]""",
        )

    def test_get_single_parent_diff(self):
        self.assertEqual(
            tidy_html_whitespace(
                self.example_person.diff_for_version("3fc494d54f61a157")
            ),
            "<dl>"
            "<dt>Changes made compared to parent 2f07734529a83242</dt>"
            '<dd><p class="version-diff"><span class="version-op-add">Added: other_names/0/note =&gt; &quot;Maiden name&quot;</span><br/></p></dd>'
            "</dl>",
        )

    def test_get_zero_parent_diff(self):
        self.assertEqual(
            tidy_html_whitespace(
                self.example_person.diff_for_version("2f07734529a83242")
            ),
            """<dl><dt>Changes made in initial version</dt><dd><p class="version-diff"><span class="version-op-add">Added: honorific_prefix =&gt; &quot;Mrs&quot;</span><br/><span class="version-op-add">Added: id =&gt; &quot;6704&quot;</span><br/><span class="version-op-add">Added: name =&gt; &quot;Sarah Jones&quot;</span><br/><span class="version-op-add">Added: other_names =&gt; [ { &quot;name&quot;: &quot;Sarah Smith&quot; } ]</span><br/></p></dd></dl>""",
        )

    def test_include_inline_style_colouring(self):
        self.assertEqual(
            tidy_html_whitespace(
                self.example_person.diff_for_version(
                    "3fc494d54f61a157", inline_style=True
                )
            ),
            "<dl>"
            "<dt>Changes made compared to parent 2f07734529a83242</dt>"
            '<dd><p class="version-diff"><span class="version-op-add" style="color: #0a6b0c">Added: other_names/0/note =&gt; &quot;Maiden name&quot;</span><br/></p></dd>'
            "</dl>",
        )
