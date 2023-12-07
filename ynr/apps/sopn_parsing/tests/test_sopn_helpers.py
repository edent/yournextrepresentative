import contextlib
import os
from os.path import abspath, dirname, join
from tempfile import NamedTemporaryFile
from unittest import skipIf

import boto3
import pytest
from candidates.tests.factories import (
    BallotPaperFactory,
    ElectionFactory,
    OrganizationFactory,
)
from django.core.files import File
from django.test import TestCase
from mock import patch
from moto import mock_s3
from official_documents.models import OfficialDocument, TextractResult
from sopn_parsing.helpers.extract_pages import (
    TextractSOPNHelper,
    TextractSOPNParsingHelper,
)
from sopn_parsing.helpers.text_helpers import NoTextInDocumentError, clean_text
from sopn_parsing.tests import should_skip_pdf_tests

with contextlib.suppress(ImportError):
    from sopn_parsing.helpers.pdf_helpers import SOPNDocument


class TestSOPNHelpers(TestCase):
    def test_clean_text(self):
        text = "\n C andidates (Namés)"
        self.assertEqual(clean_text(text), "candidates")

    def test_clean_text_removes_digits(self):
        for text in [
            "enwr ymgeisydd candidate name5",
            "enwr ymgeisydd candidate name 5",
            "enwr ymgeisydd candidate name\n5",
        ]:
            with self.subTest(msg=text):
                self.assertEqual(
                    clean_text(text), "enwr ymgeisydd candidate name"
                )

    def test_empty_documents(self):
        example_doc_path = abspath(
            join(dirname(__file__), "data/sopn-berkeley-vale.pdf")
        )
        with open(example_doc_path, "rb") as f:
            sopn_file = File(f)
            doc = SOPNDocument(
                file=sopn_file,
                source_url="http://example.com",
                election_date="2019-02-28",
            )
        doc.heading = {"reason", "2019", "a", "election", "the", "labour"}
        self.assertEqual(len(doc.pages), 1)
        self.assertEqual(doc.blank_doc, False)
        self.assertRaises(NoTextInDocumentError)

    @skipIf(should_skip_pdf_tests(), "Required PDF libs not installed")
    def test_sopn_document(self):
        example_doc_path = abspath(
            join(dirname(__file__), "data/sopn-berkeley-vale.pdf")
        )
        with open(example_doc_path, "rb") as f:
            sopn_file = File(f)
            doc = SOPNDocument(
                sopn_file,
                source_url="http://example.com",
                election_date="2022-02-28",
            )
        self.assertSetEqual(
            doc.document_heading_set,
            {
                # Header
                "the",
                "statement",
                "of",
                "persons",
                "nominated",
                "for",
                "stroud",
                "district",
                "berkeley",
                "vale",
                "council",
                "on",
                "thursday",
                "february",
                # table headers
                "candidate",
                "name",
                "description",
                "proposer",
                "reason",
                "why",
                "no",
                "longer",
                "(if",
                "any)",
                # candidates
                "simpson",
                "jane",
                "eleanor",
                "liz",
                "ashton",
                "lindsey",
                "simpson",
                "labour",
                "green",
                "party",
                # More words here?
                "election",
                "a",
                "councillor",
                "following",
                "is",
                "as",
            },
        )

        self.assertEqual(len(doc.pages), 1)

    @skipIf(should_skip_pdf_tests(), "Required PDF libs not installed")
    def test_single_page_sopn(self):
        example_doc_path = abspath(
            join(dirname(__file__), "data/sopn-berkeley-vale.pdf")
        )
        ballot = BallotPaperFactory(
            ballot_paper_id="local.stroud.berkeley-vale.by.2019-02-28"
        )
        with open(example_doc_path, "rb") as f:
            sopn_file = File(f)
            official_document = OfficialDocument(
                ballot=ballot,
                source_url="http://example.com/strensall",
                document_type=OfficialDocument.NOMINATION_PAPER,
            )
            official_document.uploaded_file.save(
                name="sopn.pdf", content=sopn_file
            )
            official_document.save()
            self.assertEqual(official_document.relevant_pages, "")

            document_obj = SOPNDocument(
                file=sopn_file,
                source_url="http://example.com/strensall",
                election_date=ballot.election.election_date,
            )
            self.assertEqual(len(document_obj.pages), 1)

            document_obj.match_all_pages()
            self.assertEqual(ballot.sopn.relevant_pages, "all")

    @skipIf(should_skip_pdf_tests(), "Required PDF libs not installed")
    def test_multipage_doc(self):
        """
        Uses the example of a multipage PDF which contains SOPN's for two
        ballots.
        Creates the ballots, then parses the document, and checks that the
        correct pages have been assigned to the OfficialDocument object
        related to the ballot.
        """
        example_doc_path = abspath(
            join(dirname(__file__), "data/NI-Assembly-Election-2016.pdf")
        )
        election = ElectionFactory(
            slug="nia.2016-05-05", election_date="2016-05-05"
        )
        organization = OrganizationFactory(slug="nia:nia")
        mid_ulster = BallotPaperFactory(
            ballot_paper_id="nia.mid-ulster.2016-05-05",
            election=election,
            post__label="mid ulster",
            post__organization=organization,
        )
        north_antrim = BallotPaperFactory(
            ballot_paper_id="nia.north-antrim.2016-05-05",
            election=election,
            post__label="north antrim",
            post__organization=organization,
        )
        with open(example_doc_path, "rb") as f:
            sopn_file = File(f)
            # assign the same PDF to both ballots with the same source URL
            for ballot in [north_antrim, mid_ulster]:
                official_document = OfficialDocument(
                    ballot=ballot,
                    source_url="http://example.com",
                    document_type=OfficialDocument.NOMINATION_PAPER,
                )
                official_document.uploaded_file.save(
                    name="sopn.pdf", content=sopn_file
                )
                official_document.save()
                self.assertEqual(official_document.relevant_pages, "")

            document_obj = SOPNDocument(
                file=sopn_file,
                source_url="http://example.com",
                election_date=election.election_date,
            )
        self.assertEqual(len(document_obj.pages), 9)
        document_obj.match_all_pages()

        self.assertEqual(mid_ulster.sopn.relevant_pages, "1,2,3,4")
        self.assertEqual(north_antrim.sopn.relevant_pages, "5,6,7,8,9")

    @skipIf(should_skip_pdf_tests(), "Required PDF libs not installed")
    def test_document_with_identical_headers(self):
        """
        Uses an example PDF where the two headers are identical to check that
        the second page is recognised as a continuation of the previous page
        """
        sopn_pdf = abspath(
            join(dirname(__file__), "data/local.york.strensall.2019-05-02.pdf")
        )
        strensall = BallotPaperFactory(
            ballot_paper_id="local.york.strensall.2019-05-02",
            post__label="Strensall",
        )
        with open(sopn_pdf, "rb") as f:
            sopn_file = File(f)
            official_document = OfficialDocument(
                ballot=strensall,
                source_url="http://example.com/strensall",
                document_type=OfficialDocument.NOMINATION_PAPER,
            )
            official_document.uploaded_file.save(
                name="sopn.pdf", content=sopn_file
            )
            official_document.save()
            self.assertEqual(official_document.relevant_pages, "")

            document_obj = SOPNDocument(
                file=sopn_file,
                source_url="http://example.com/strensall",
                election_date=strensall.election.election_date,
            )
        self.assertEqual(len(document_obj.pages), 2)

        document_obj.match_all_pages()
        self.assertEqual(strensall.sopn.relevant_pages, "all")


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture
def s3_client(aws_credentials):
    with mock_s3():
        conn = boto3.client("s3", region_name="eu-west-2")
        yield conn


@pytest.fixture
def bucket_name(settings):
    settings.TEXTRACT_S3_BUCKET_NAME = "my-test-bucket"
    yield settings.TEXTRACT_S3_BUCKET_NAME


@pytest.fixture
def s3_bucket(s3_client, bucket_name):
    s3_client.create_bucket(
        ACL="public-read-write",
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )
    yield


@pytest.fixture
def textract_sopn_helper(db, s3_client, s3_bucket):
    official_document = OfficialDocument.objects.create(
        ballot=BallotPaperFactory(),
        document_type=OfficialDocument.NOMINATION_PAPER,
    )
    yield TextractSOPNHelper(official_document=official_document)


def test_list_buckets(s3_client, s3_bucket):
    my_client = MyS3Client()
    buckets = my_client.list_buckets()
    assert ["my-test-bucket"] == buckets


def list_objects(self, bucket_name, prefix):
    """Returns a list all objects with specified prefix."""
    response = self.client.list_objects(
        Bucket=bucket_name,
        Prefix=prefix,
    )
    return [object["Key"] for object in response["Contents"]]


def test_list_objects(s3_client, s3_bucket):
    file_text = "test"
    with NamedTemporaryFile(delete=True, suffix=".txt") as tmp:
        with open(tmp.name, "w", encoding="UTF-8") as f:
            f.write(file_text)

        s3_client.upload_file(tmp.name, "my-test-bucket", "file12")
        s3_client.upload_file(tmp.name, "my-test-bucket", "file22")

    my_client = MyS3Client()
    objects = my_client.list_objects(
        bucket_name="my-test-bucket", prefix="file1"
    )
    assert objects == ["file12"]


def test_upload_to_s3(textract_sopn_helper):
    assert textract_sopn_helper.s3_key == (
        "test/test_sopn.pdf",
        "my-test-bucket",
    )
    response = textract_sopn_helper.upload_to_s3()
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200


def test_start_detection(textract_sopn_helper):
    with patch(
        "sopn_parsing.helpers.extract_pages.TextractSOPNHelper.textract_start_document_analysis"
    ) as mock_textract_start_document_analysis:
        mock_textract_start_document_analysis.return_value = {"JobId": "1234"}
        textract_result = textract_sopn_helper.start_detection()
    assert textract_result.job_id == "1234"
    # I haven't been able to get this test to work on it's own,
    # but it works when run with the other tests
    assert textract_result.analysis_status == "NOT_STARTED"
    with patch(
        "sopn_parsing.helpers.extract_pages.TextractSOPNHelper.textract_get_document_analysis"
    ) as mock_textract_get_document_analysis:
        mock_textract_get_document_analysis.return_value = (
            get_document_analysis_json
        )
        textract_sopn_helper.update_job_status()
    assert official_document.textract_result.analysis_status == "SUCCEEDED"


def test_update_job_status_failed(textract_sopn_helper, failed_analysis):
    official_document = textract_sopn_helper.official_document
    TextractResult.objects.create(
        official_document=official_document,
        job_id="1234",
        json_response="",
        analysis_status="NOT_STARTED",
    )

    with patch(
        "sopn_parsing.helpers.extract_pages.TextractSOPNHelper.textract_get_document_analysis"
    ) as mock_textract_get_document_analysis:
        mock_textract_get_document_analysis.return_value = failed_analysis
        textract_sopn_helper.update_job_status()
    assert official_document.textract_result.analysis_status == "FAILED"


def analysis_with_next_token_side_effect(job_id, next_token=None):
    if next_token == "token":
        return {"JobStatus": "SUCCEEDED", "Blocks": ["foo", "Bar"]}
    return {"JobStatus": "SUCCEEDED", "NextToken": "token", "Blocks": ["baz"]}


def test_update_job_status_with_token(textract_sopn_helper):
    official_document = textract_sopn_helper.official_document
    TextractResult.objects.create(
        official_document=official_document,
        job_id="1234",
        json_response="",
        analysis_status="NOT_STARTED",
    )

    with patch(
        "sopn_parsing.helpers.extract_pages.TextractSOPNHelper.textract_get_document_analysis",
        side_effect=analysis_with_next_token_side_effect,
    ) as mock_textract_get_document_analysis:
        mock_textract_get_document_analysis.return_value = Mock(
            side_effect=analysis_with_next_token_side_effect
        )
        textract_sopn_helper.update_job_status()
    assert official_document.textract_result.analysis_status == "SUCCEEDED"
    assert (
        official_document.textract_result.json_response
        == '{"JobStatus": "SUCCEEDED", "Blocks": ["baz", "foo", "Bar"]}'
    )


@pytest.fixture
def textract_sopn_parsing_helper(
    db, s3_client, s3_bucket, get_document_analysis_json
):
    official_document = OfficialDocument.objects.create(
        ballot=BallotPaperFactory(),
        document_type=OfficialDocument.NOMINATION_PAPER,
    )
    textract_result = TextractResult.objects.create(
        official_document=official_document,
        job_id="1234",
        json_response=get_document_analysis_json,
        analysis_status="SUCCEEDED",
    )
    yield TextractSOPNParsingHelper(
        official_document=official_document, textract_result=textract_result
    )


def test_create_df_from_textract_result(textract_sopn_parsing_helper):
    # assert that get_rows_columns_map is called once
    df = textract_sopn_parsing_helper.create_df_from_textract_result(
        official_document=textract_sopn_parsing_helper.official_document,
        textract_result=textract_sopn_parsing_helper.textract_result,
    )

    sopn_text = "STATEMENT OF PERSONS"
    assert sopn_text in df.values


@pytest.fixture
def textract_sopn_parsing_helper(db, s3_client, s3_bucket):
    official_document = OfficialDocument.objects.create(
        ballot=BallotPaperFactory(),
        document_type=OfficialDocument.NOMINATION_PAPER,
    )
    textract_result = TextractResult.objects.create(
        official_document=official_document,
        job_id="1234",
        # use the json response from ynr/apps/sopn_parsing/tests/data/sample_textract_response.json
        json_response={
            "DocumentMetadata": {"Pages": 1},
            "JobStatus": "SUCCEEDED",
            "Blocks": [
                {
                    "BlockType": "PAGE",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 1,
                            "Height": 1,
                            "Left": 0,
                            "Top": 0,
                        },
                        "Polygon": [
                            {"X": 0, "Y": 3.0419303698181466e-7},
                            {"X": 1, "Y": 0},
                            {"X": 1, "Y": 1},
                            {"X": 5.420919819698611e-7, "Y": 1},
                        ],
                    },
                    "Id": "3b7b4bda-5c45-4b2f-a2fc-11b42888e157",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "fb1d266c-ec77-4cc2-9122-713f7880700a",
                                "f0fd897e-d29a-491c-9847-5edd6d8dad50",
                                "8e5c52e5-7505-4456-b290-aff71e494c98",
                                "e8e8b5ab-c4ad-468f-ba5a-6e2777459ab0",
                                "4b071f63-e999-4843-8e95-4cab73b8faf9",
                                "05e4e250-62fe-4092-a524-d309322327f0",
                                "2712cdab-9041-4ad2-af06-8fa3f21916ba",
                                "42aa368e-0a8c-43ed-964e-74b8b1b43e75",
                                "5e0addca-3d86-449c-a334-48355725dd04",
                                "c78ed836-822d-4f49-8e6b-0aafd0a0bf4c",
                                "5d5622b9-10e3-45e2-8089-d81ec66f2695",
                                "dedb9a99-ebe2-451b-82c7-09e957cfc0f7",
                                "a3264ef2-91b6-44e6-a117-242fb500758d",
                                "0d17e161-6c53-451e-bd9e-8b062dbd6dc2",
                                "8b047907-0561-4b1e-abd0-67f3b7fc7f26",
                                "16abb038-3912-4f68-b951-deb3649804dc",
                                "664327dd-b793-4506-82c1-679509493dd8",
                                "43f95fb1-785a-4c99-8c1b-b5278fcbc5bd",
                                "67525a2e-62da-47ec-babd-a6f4f46e2c51",
                                "ff39f20e-ce54-4a2e-9656-7b57ffd723e1",
                                "dbdf463c-5b17-4bec-a8f3-7d9520e1d8a3",
                                "2177453a-6481-41d0-876c-f1e481aa61c4",
                                "0d270d12-7647-4a90-83ff-fc71acdbf034",
                                "8cef72d8-840b-46be-923d-581bb9e1b713",
                                "8dba6144-e481-4400-b814-ea858bf1597f",
                                "e7d5ccaf-5b83-4d64-ad30-277b24f1208e",
                                "37446e0b-a9ed-408d-be0e-0d62e4653afd",
                                "5ee7444d-4c03-45ea-ae87-604cae9b2d9d",
                                "0acecfde-9b52-4bf4-96e9-20a99f165854",
                                "1477f871-08b9-4b79-b6ec-a010587a32b9",
                                "f50b6708-6b7f-42b7-b7d5-49e5b0fbf6c7",
                                "6f3572e7-511a-4cbd-a1e1-32a56446bbd9",
                                "7d6fd27e-d9c0-449e-8c36-2c99639f16e1",
                                "401014fd-f9ec-4c72-893d-e6bbe278a0d7",
                                "cf098d77-216c-4352-81db-9ea78ce3e0ee",
                                "d9617636-c18f-4a03-ab62-71050aab692c",
                                "09647b30-44ce-4ca0-9eb1-6390f3432b8e",
                                "6cdebb37-e4b1-4b77-912d-de8b032f9309",
                                "62df2d7a-098b-494e-94cd-668d422eac5c",
                                "5ce8f47c-22a8-43c2-91af-b7a5f65c2ab4",
                                "bd0a10a5-ff47-431d-88a1-b3b23849bfe7",
                                "3dde21f5-f787-42e9-a40b-ef83c97cdb53",
                                "cb3492ff-3ad7-4eda-9005-3307ea319b1a",
                                "40936e43-27f1-4c55-9ec3-2143741f4ff3",
                                "f35529e4-1f89-4578-b8b1-aefcae596150",
                                "1f5503e8-955b-44de-bb53-b1cfd9791bde",
                                "f1415a15-ac5f-495d-b0c3-f57afb4351a0",
                                "b5fef35f-2e36-44f1-919a-1235a4bbac43",
                                "3b25330f-5518-4f0b-8de6-e9a9dc37d751",
                                "bfb9cb24-3d8f-4800-9bab-fe8786183e36",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.96359252929688,
                    "Text": "STATEMENT OF PERSONS",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.7803550958633423,
                            "Height": 0.03399920091032982,
                            "Left": 0.11023641377687454,
                            "Top": 0.04087038338184357,
                        },
                        "Polygon": [
                            {"X": 0.11023641377687454, "Y": 0.0413246750831604},
                            {"X": 0.8905614614486694, "Y": 0.04087038338184357},
                            {"X": 0.8905915021896362, "Y": 0.07441917061805725},
                            {
                                "X": 0.11025737226009369,
                                "Y": 0.07486958056688309,
                            },
                        ],
                    },
                    "Id": "fb1d266c-ec77-4cc2-9122-713f7880700a",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "49a7823b-f1ec-4297-91fb-199a0452ab7d",
                                "4bd8e7b9-8173-47f9-b416-65f7cef7dd84",
                                "80397ad2-5d48-4b7d-a9e4-6c9ff93d80ac",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.92805480957031,
                    "Text": "NOMINATED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.36702030897140503,
                            "Height": 0.03284572437405586,
                            "Left": 0.3171496093273163,
                            "Top": 0.09061070531606674,
                        },
                        "Polygon": [
                            {"X": 0.3171496093273163, "Y": 0.09082166105508804},
                            {"X": 0.68414306640625, "Y": 0.09061070531606674},
                            {"X": 0.6841699481010437, "Y": 0.12324725091457367},
                            {"X": 0.3171723484992981, "Y": 0.1234564334154129},
                        ],
                    },
                    "Id": "f0fd897e-d29a-491c-9847-5edd6d8dad50",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["c4e02eaa-b43e-4500-91ab-7bd812fd1933"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.96357727050781,
                    "Text": "London Borough of Lewisham",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.4344790279865265,
                            "Height": 0.021653590723872185,
                            "Left": 0.28295084834098816,
                            "Top": 0.14722102880477905,
                        },
                        "Polygon": [
                            {
                                "X": 0.28295084834098816,
                                "Y": 0.14746710658073425,
                            },
                            {"X": 0.717411994934082, "Y": 0.14722102880477905},
                            {"X": 0.7174298763275146, "Y": 0.16862991452217102},
                            {"X": 0.2829654812812805, "Y": 0.1688746064901352},
                        ],
                    },
                    "Id": "8e5c52e5-7505-4456-b290-aff71e494c98",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "3f6c0814-cac0-4d56-a486-7056cdd8e91d",
                                "27191b33-9616-4965-98c9-22f626b45b42",
                                "c7290639-f2bd-42ff-a6a8-ab3ccfc0a81c",
                                "49bda281-4097-4879-a826-0d6f47d90c97",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.92741394042969,
                    "Text": "Election of a Councillor",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.6705235838890076,
                            "Height": 0.03401198983192444,
                            "Left": 0.16627052426338196,
                            "Top": 0.18812774121761322,
                        },
                        "Polygon": [
                            {"X": 0.16627052426338196, "Y": 0.1885034292936325},
                            {"X": 0.8367646336555481, "Y": 0.18812774121761322},
                            {"X": 0.8367941379547119, "Y": 0.2217673659324646},
                            {"X": 0.1662921905517578, "Y": 0.22213971614837646},
                        ],
                    },
                    "Id": "e8e8b5ab-c4ad-468f-ba5a-6e2777459ab0",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "26587598-2085-4046-be81-df48ac455c21",
                                "4715d5d4-8596-43c8-8dea-4b19d5029d29",
                                "fb344ff5-8e59-4000-8c83-3102199cd778",
                                "6fadb6e2-cb46-4854-93fe-a40daea8e8c5",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.98600769042969,
                    "Text": "The following is a statement of the persons nominated for election as Borough",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.8112342953681946,
                            "Height": 0.01756424456834793,
                            "Left": 0.09331536293029785,
                            "Top": 0.24443961679935455,
                        },
                        "Polygon": [
                            {
                                "X": 0.09331536293029785,
                                "Y": 0.24488738179206848,
                            },
                            {"X": 0.9045342206954956, "Y": 0.24443961679935455},
                            {"X": 0.9045496582984924, "Y": 0.2615581452846527},
                            {"X": 0.09332595765590668, "Y": 0.2620038688182831},
                        ],
                    },
                    "Id": "4b071f63-e999-4843-8e95-4cab73b8faf9",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "29ac063b-a32c-4741-bcdb-1436e6e513ad",
                                "506e1bde-a82d-4b9a-8092-883dcb16561c",
                                "abd22fbb-0a26-4e5e-861f-108f08e5a2c0",
                                "73144b29-b016-4829-8b12-c27793fa7f68",
                                "80a5659b-aa3a-4141-9bb8-7d4a88bd3401",
                                "3c4922ef-c194-4de3-81e3-9c2db62b6dc8",
                                "0a00517b-2e73-460d-9aea-6c2adc63fdb7",
                                "dedf2347-f72b-48bc-8772-cb8d1d842da8",
                                "06948c35-9ce5-44ec-a296-56356e891085",
                                "ce059fd9-97ea-48c5-8041-d0b65c2c9e53",
                                "857acd3e-8731-4a93-a461-8b26af676c9c",
                                "6089051b-80bc-443c-907a-9307115a109a",
                                "e806155c-b17d-4478-ba27-64d8731d8186",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.93843841552734,
                    "Text": "Councillor for",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.13843965530395508,
                            "Height": 0.013468615710735321,
                            "Left": 0.43105176091194153,
                            "Top": 0.26384276151657104,
                        },
                        "Polygon": [
                            {
                                "X": 0.43105176091194153,
                                "Y": 0.26391878724098206,
                            },
                            {"X": 0.5694808959960938, "Y": 0.26384276151657104},
                            {"X": 0.5694913864135742, "Y": 0.27723565697669983},
                            {
                                "X": 0.43106162548065186,
                                "Y": 0.27731138467788696,
                            },
                        ],
                    },
                    "Id": "05e4e250-62fe-4092-a524-d309322327f0",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "f9fc4e14-6e9e-4fd6-9cf4-994fe4aef56d",
                                "38636179-86af-44c2-abe1-c7fbb33ad891",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.95783233642578,
                    "Text": "Deptford Ward",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.4133222699165344,
                            "Height": 0.04155968874692917,
                            "Left": 0.29390066862106323,
                            "Top": 0.300707072019577,
                        },
                        "Polygon": [
                            {
                                "X": 0.29390066862106323,
                                "Y": 0.30093175172805786,
                            },
                            {"X": 0.707188606262207, "Y": 0.300707072019577},
                            {"X": 0.7072229385375977, "Y": 0.3420445919036865},
                            {"X": 0.2939291298389435, "Y": 0.3422667384147644},
                        ],
                    },
                    "Id": "2712cdab-9041-4ad2-af06-8fa3f21916ba",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "a7e4229a-909d-4c24-9cd1-d89f4f855d56",
                                "44145c2a-aaf7-4303-9c31-ddecfb452941",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.96171569824219,
                    "Text": "Name of",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07948797941207886,
                            "Height": 0.011393491178750992,
                            "Left": 0.09993816912174225,
                            "Top": 0.37091970443725586,
                        },
                        "Polygon": [
                            {
                                "X": 0.09993816912174225,
                                "Y": 0.37096208333969116,
                            },
                            {
                                "X": 0.17941878736019135,
                                "Y": 0.37091970443725586,
                            },
                            {"X": 0.1794261485338211, "Y": 0.3822709321975708},
                            {
                                "X": 0.09994521737098694,
                                "Y": 0.38231319189071655,
                            },
                        ],
                    },
                    "Id": "42aa368e-0a8c-43ed-964e-74b8b1b43e75",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "a9f9e43f-7609-455b-ad04-07ed57a4cb65",
                                "8ce5fe8e-40e6-49ee-a94e-f8cb11bb1772",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.92391204833984,
                    "Text": "Description",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.11043643206357956,
                            "Height": 0.014214947819709778,
                            "Left": 0.2903299331665039,
                            "Top": 0.37070953845977783,
                        },
                        "Polygon": [
                            {"X": 0.2903299331665039, "Y": 0.3707684278488159},
                            {"X": 0.4007561206817627, "Y": 0.37070953845977783},
                            {"X": 0.40076637268066406, "Y": 0.3848658502101898},
                            {"X": 0.2903396785259247, "Y": 0.3849245011806488},
                        ],
                    },
                    "Id": "5e0addca-3d86-449c-a334-48355725dd04",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["242f76e7-5def-49a6-a2f6-4ab5243be636"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.96614837646484,
                    "Text": "Home Address",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14176860451698303,
                            "Height": 0.011580155231058598,
                            "Left": 0.5137354731559753,
                            "Top": 0.3791646957397461,
                        },
                        "Polygon": [
                            {"X": 0.5137354731559753, "Y": 0.37924012541770935},
                            {"X": 0.6554946899414062, "Y": 0.3791646957397461},
                            {"X": 0.655504047870636, "Y": 0.39066970348358154},
                            {"X": 0.5137442350387573, "Y": 0.3907448649406433},
                        ],
                    },
                    "Id": "c78ed836-822d-4f49-8e6b-0aafd0a0bf4c",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "234e99b5-8bf4-4526-9a02-1549d1fe03f7",
                                "be277113-f9df-483f-b9be-e310461400a6",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.34394836425781,
                    "Text": "Proposer (*)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.11453074961900711,
                            "Height": 0.014271654188632965,
                            "Left": 0.7166520357131958,
                            "Top": 0.37069186568260193,
                        },
                        "Polygon": [
                            {"X": 0.7166520357131958, "Y": 0.3707529306411743},
                            {"X": 0.831170380115509, "Y": 0.37069186568260193},
                            {"X": 0.8311827778816223, "Y": 0.384902685880661},
                            {"X": 0.7166638970375061, "Y": 0.3849635124206543},
                        ],
                    },
                    "Id": "5d5622b9-10e3-45e2-8089-d81ec66f2695",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "bffcbf83-fc0a-4e56-ab69-abcf8746c60d",
                                "f86a7008-8399-463c-98b8-3ce5568392cc",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.9234390258789,
                    "Text": "Candidate",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09670990705490112,
                            "Height": 0.01165726874023676,
                            "Left": 0.09970410913228989,
                            "Top": 0.3870118260383606,
                        },
                        "Polygon": [
                            {"X": 0.09970410913228989, "Y": 0.3870631754398346},
                            {"X": 0.19640642404556274, "Y": 0.3870118260383606},
                            {"X": 0.1964140087366104, "Y": 0.3986179232597351},
                            {"X": 0.09971132129430771, "Y": 0.3986690938472748},
                        ],
                    },
                    "Id": "dedb9a99-ebe2-451b-82c7-09e957cfc0f7",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["5e590528-70c2-45d1-bdf4-ff7f6f714c5d"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.93638610839844,
                    "Text": "(if any)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06527645140886307,
                            "Height": 0.014412468299269676,
                            "Left": 0.2903864085674286,
                            "Top": 0.3868895173072815,
                        },
                        "Polygon": [
                            {"X": 0.2903864085674286, "Y": 0.386924147605896},
                            {"X": 0.35565266013145447, "Y": 0.3868895173072815},
                            {
                                "X": 0.35566285252571106,
                                "Y": 0.40126746892929077,
                            },
                            {"X": 0.2903963029384613, "Y": 0.4013019800186157},
                        ],
                    },
                    "Id": "a3264ef2-91b6-44e6-a117-242fb500758d",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "580803c9-819f-4f6e-bcdb-e7de5019e7ff",
                                "7ea780e7-92a5-427e-89f3-0dc549ecb461",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.19596862792969,
                    "Text": "Seconder (**)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.12660787999629974,
                            "Height": 0.014631995931267738,
                            "Left": 0.7161911725997925,
                            "Top": 0.3868173062801361,
                        },
                        "Polygon": [
                            {"X": 0.7161911725997925, "Y": 0.38688451051712036},
                            {"X": 0.8427862524986267, "Y": 0.3868173062801361},
                            {"X": 0.8427990674972534, "Y": 0.40138235688209534},
                            {"X": 0.7162033319473267, "Y": 0.4014492928981781},
                        ],
                    },
                    "Id": "0d17e161-6c53-451e-bd9e-8b062dbd6dc2",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "53b78b39-8da4-4882-8d97-08e2566cba2b",
                                "9bdcb99b-63be-4c07-8200-780eaa7a1052",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.92437744140625,
                    "Text": "ATKINSON",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1367911696434021,
                            "Height": 0.01499776542186737,
                            "Left": 0.09905943274497986,
                            "Top": 0.42948994040489197,
                        },
                        "Polygon": [
                            {
                                "X": 0.09905943274497986,
                                "Y": 0.42956170439720154,
                            },
                            {
                                "X": 0.23584063351154327,
                                "Y": 0.42948994040489197,
                            },
                            {
                                "X": 0.23585060238838196,
                                "Y": 0.44441625475883484,
                            },
                            {
                                "X": 0.09906869381666183,
                                "Y": 0.44448772072792053,
                            },
                        ],
                    },
                    "Id": "8b047907-0561-4b1e-abd0-67f3b7fc7f26",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["86ab1721-778c-48f6-b8bf-bceb608ed834"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.92857360839844,
                    "Text": "Labour Party",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.13434693217277527,
                            "Height": 0.016406632959842682,
                            "Left": 0.2904919683933258,
                            "Top": 0.4412554204463959,
                        },
                        "Polygon": [
                            {"X": 0.2904919683933258, "Y": 0.44132566452026367},
                            {"X": 0.4248269200325012, "Y": 0.4412554204463959},
                            {"X": 0.4248389005661011, "Y": 0.4575921595096588},
                            {"X": 0.2905031740665436, "Y": 0.45766204595565796},
                        ],
                    },
                    "Id": "16abb038-3912-4f68-b951-deb3649804dc",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "866e95ae-7b61-45ae-9afe-b699b7116799",
                                "0d20e06b-f27e-462c-b680-ad3787221ec0",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.90521240234375,
                    "Text": "(address in London",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1281856745481491,
                            "Height": 0.01060364581644535,
                            "Left": 0.5141233801841736,
                            "Top": 0.43717435002326965,
                        },
                        "Polygon": [
                            {"X": 0.5141233801841736, "Y": 0.43724143505096436},
                            {"X": 0.642300546169281, "Y": 0.43717435002326965},
                            {"X": 0.6423090696334839, "Y": 0.44771111011505127},
                            {"X": 0.5141314268112183, "Y": 0.44777798652648926},
                        ],
                    },
                    "Id": "664327dd-b793-4506-82c1-679509493dd8",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "f8b20245-5eda-4e3a-8b06-ff430aee2f74",
                                "d9b1ccb3-0d5e-40ac-9fcd-1b66e77ad61c",
                                "c8e485de-fc22-4f0d-9158-57adadd59f85",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.2626724243164,
                    "Text": "Garvey Redmond *",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1284562200307846,
                            "Height": 0.010949688963592052,
                            "Left": 0.7161666750907898,
                            "Top": 0.43719616532325745,
                        },
                        "Polygon": [
                            {"X": 0.7161666750907898, "Y": 0.4372633993625641},
                            {"X": 0.8446133732795715, "Y": 0.43719616532325745},
                            {"X": 0.8446229100227356, "Y": 0.44807884097099304},
                            {"X": 0.7161757946014404, "Y": 0.44814586639404297},
                        ],
                    },
                    "Id": "43f95fb1-785a-4c99-8c1b-b5278fcbc5bd",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "3a36e0a8-141f-47f3-8314-689e855edb51",
                                "f0008340-40c6-4e43-add1-7ee225330958",
                                "aceae24d-43a5-45d3-8de9-fe14998cefb3",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.98502349853516,
                    "Text": "Dawn",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06620199978351593,
                            "Height": 0.01482323743402958,
                            "Left": 0.10078901052474976,
                            "Top": 0.45143911242485046,
                        },
                        "Polygon": [
                            {"X": 0.10078901052474976, "Y": 0.4514736235141754},
                            {
                                "X": 0.16698148846626282,
                                "Y": 0.45143911242485046,
                            },
                            {
                                "X": 0.16699101030826569,
                                "Y": 0.46622800827026367,
                            },
                            {"X": 0.10079820454120636, "Y": 0.4662623703479767},
                        ],
                    },
                    "Id": "67525a2e-62da-47ec-babd-a6f4f46e2c51",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["7e2843e4-4ad1-4bdd-a713-45d5f15ab9fe"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 98.58590698242188,
                    "Text": "Borough of Lewisham)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.15050268173217773,
                            "Height": 0.01092724408954382,
                            "Left": 0.5134903192520142,
                            "Top": 0.44957640767097473,
                        },
                        "Polygon": [
                            {"X": 0.5134903192520142, "Y": 0.44965487718582153},
                            {"X": 0.6639841198921204, "Y": 0.44957640767097473},
                            {"X": 0.6639929413795471, "Y": 0.46042540669441223},
                            {"X": 0.5134986042976379, "Y": 0.46050363779067993},
                        ],
                    },
                    "Id": "ff39f20e-ce54-4a2e-9656-7b57ffd723e1",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "170b7f6c-14b7-4098-b8fd-3bfb77e4e3c5",
                                "d38cac70-f4bf-483a-931d-b47c96b5a1af",
                                "d7b1ef34-dec6-443d-b00d-bd217f46f580",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 98.77979278564453,
                    "Text": "Kelly Nicholas J **",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.12198073416948318,
                            "Height": 0.010853397659957409,
                            "Left": 0.7161106467247009,
                            "Top": 0.44958803057670593,
                        },
                        "Polygon": [
                            {"X": 0.7161106467247009, "Y": 0.4496516287326813},
                            {"X": 0.838081955909729, "Y": 0.44958803057670593},
                            {"X": 0.8380913734436035, "Y": 0.4603779911994934},
                            {"X": 0.716119647026062, "Y": 0.4604414105415344},
                        ],
                    },
                    "Id": "dbdf463c-5b17-4bec-a8f3-7d9520e1d8a3",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "992b1de9-381b-4bc4-ad75-7a45263be98f",
                                "87f23f18-72e4-4082-b37c-f6eeb720e269",
                                "304276a9-b4f5-459c-a124-dd47d9bca6ba",
                                "a8e6fc18-9109-4ad2-a1aa-6a1e7de652ea",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.96228790283203,
                    "Text": "CROSSLEY",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14634709060192108,
                            "Height": 0.015371249057352543,
                            "Left": 0.0993841141462326,
                            "Top": 0.4926571846008301,
                        },
                        "Polygon": [
                            {"X": 0.0993841141462326, "Y": 0.49273258447647095},
                            {"X": 0.24572092294692993, "Y": 0.4926571846008301},
                            {"X": 0.2457312047481537, "Y": 0.507953405380249},
                            {"X": 0.09939361363649368, "Y": 0.5080284476280212},
                        ],
                    },
                    "Id": "2177453a-6481-41d0-876c-f1e481aa61c4",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["cb0e1407-68fb-4e62-b2bf-55e30ee99551"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.93112182617188,
                    "Text": "(address in London",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1284865438938141,
                            "Height": 0.010750724002718925,
                            "Left": 0.513847827911377,
                            "Top": 0.500658392906189,
                        },
                        "Polygon": [
                            {"X": 0.513847827911377, "Y": 0.5007244348526001},
                            {"X": 0.642325758934021, "Y": 0.500658392906189},
                            {"X": 0.6423344016075134, "Y": 0.5113433003425598},
                            {"X": 0.5138559937477112, "Y": 0.5114091038703918},
                        ],
                    },
                    "Id": "0d270d12-7647-4a90-83ff-fc71acdbf034",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "d632bbcb-6cc5-4d16-b415-536aec2c710b",
                                "749e5eff-88b1-4787-ba36-1f9313cc6a47",
                                "7d275e50-6760-4807-8334-06e0bf2550c1",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 98.57149505615234,
                    "Text": "Wilmer Tania L *",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1117529347538948,
                            "Height": 0.009152291342616081,
                            "Left": 0.7153986692428589,
                            "Top": 0.5003470778465271,
                        },
                        "Polygon": [
                            {"X": 0.7153986692428589, "Y": 0.5004044771194458},
                            {"X": 0.827143669128418, "Y": 0.5003470778465271},
                            {"X": 0.8271515965461731, "Y": 0.5094420313835144},
                            {"X": 0.7154062390327454, "Y": 0.5094993710517883},
                        ],
                    },
                    "Id": "8cef72d8-840b-46be-923d-581bb9e1b713",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "0c839e20-32c2-44b5-8231-0398d070ef94",
                                "030474e7-f8ae-4ab6-9e04-729cdf28b6b1",
                                "d775da41-7115-4ac1-aa79-36da86297306",
                                "3242e208-247c-43c3-9da4-80cff653b820",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.9902572631836,
                    "Text": "The Green Party",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1740565299987793,
                            "Height": 0.016448626294732094,
                            "Left": 0.2897351384162903,
                            "Top": 0.5044050216674805,
                        },
                        "Polygon": [
                            {"X": 0.2897351384162903, "Y": 0.5044943690299988},
                            {"X": 0.4637794494628906, "Y": 0.5044050216674805},
                            {"X": 0.4637916684150696, "Y": 0.5207647085189819},
                            {"X": 0.28974637389183044, "Y": 0.5208536386489868},
                        ],
                    },
                    "Id": "8dba6144-e481-4400-b814-ea858bf1597f",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "3b68e359-ded1-4b01-bb10-3db97586d52b",
                                "50ff677b-3523-4275-adb4-d18eadae5486",
                                "961407f6-a2ac-4bab-89a6-3d6409fc31bd",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.98291015625,
                    "Text": "Tim",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04397975653409958,
                            "Height": 0.014743184670805931,
                            "Left": 0.09925346821546555,
                            "Top": 0.5147435665130615,
                        },
                        "Polygon": [
                            {"X": 0.09925346821546555, "Y": 0.5147660970687866},
                            {"X": 0.1432238668203354, "Y": 0.5147435665130615},
                            {"X": 0.14323322474956512, "Y": 0.5294643640518188},
                            {"X": 0.09926260262727737, "Y": 0.5294867753982544},
                        ],
                    },
                    "Id": "e7d5ccaf-5b83-4d64-ad30-277b24f1208e",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["c2824581-0142-497a-ba5a-d956cdd8a12b"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.0635757446289,
                    "Text": "Borough of Lewisham)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.15034334361553192,
                            "Height": 0.011025147512555122,
                            "Left": 0.5135616660118103,
                            "Top": 0.5127400159835815,
                        },
                        "Polygon": [
                            {"X": 0.5135616660118103, "Y": 0.5128170251846313},
                            {"X": 0.6638960838317871, "Y": 0.5127400159835815},
                            {"X": 0.6639050245285034, "Y": 0.5236884355545044},
                            {"X": 0.5135700702667236, "Y": 0.5237652063369751},
                        ],
                    },
                    "Id": "37446e0b-a9ed-408d-be0e-0d62e4653afd",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "b735afa1-19f8-4b2b-84c4-339a74c2010d",
                                "b2ed293f-07f6-445d-870f-6e4d83f7c5d2",
                                "46054c85-288e-40a3-9997-410df187ca99",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.28801727294922,
                    "Text": "Wiaterska Roksana M **",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.16365207731723785,
                            "Height": 0.008890360593795776,
                            "Left": 0.7155911326408386,
                            "Top": 0.5127432346343994,
                        },
                        "Polygon": [
                            {"X": 0.7155911326408386, "Y": 0.5128270387649536},
                            {"X": 0.8792353868484497, "Y": 0.5127432346343994},
                            {"X": 0.8792432546615601, "Y": 0.5215499997138977},
                            {"X": 0.7155985236167908, "Y": 0.5216335654258728},
                        ],
                    },
                    "Id": "5ee7444d-4c03-45ea-ae87-604cae9b2d9d",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "e6f7dc41-cae6-4fef-a378-df2fc2e5bd13",
                                "e79719d1-dd3d-4290-bebc-7d4b18eb9d21",
                                "d36802eb-f6d3-427b-b26f-da60171407df",
                                "53483193-3145-459e-9b17-02b144afd79b",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.9620132446289,
                    "Text": "HARDING",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.12150311470031738,
                            "Height": 0.014916855841875076,
                            "Left": 0.10060852020978928,
                            "Top": 0.5560656189918518,
                        },
                        "Polygon": [
                            {"X": 0.10060852020978928, "Y": 0.5561270713806152},
                            {"X": 0.22210177779197693, "Y": 0.5560656189918518},
                            {"X": 0.22211162745952606, "Y": 0.5709213018417358},
                            {"X": 0.10061775147914886, "Y": 0.5709824562072754},
                        ],
                    },
                    "Id": "0acecfde-9b52-4bf4-96e9-20a99f165854",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["d463cb9a-ea5a-41f1-b2de-cbf0ef461f3c"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.8660659790039,
                    "Text": "Liberal Democrats",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.18956418335437775,
                            "Height": 0.013591132126748562,
                            "Left": 0.2908428907394409,
                            "Top": 0.5675857663154602,
                        },
                        "Polygon": [
                            {"X": 0.2908428907394409, "Y": 0.5676813125610352},
                            {"X": 0.48039689660072327, "Y": 0.5675857663154602},
                            {"X": 0.48040705919265747, "Y": 0.5810816884040833},
                            {"X": 0.2908521592617035, "Y": 0.5811768770217896},
                        ],
                    },
                    "Id": "1477f871-08b9-4b79-b6ec-a010587a32b9",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "745a8e38-268b-4fe8-9c70-bc64d4ebb7c5",
                                "79a3807e-f816-47ac-9dd0-31a1c83b05ad",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.91712951660156,
                    "Text": "(address in London",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.12853989005088806,
                            "Height": 0.010703625157475471,
                            "Left": 0.5137732625007629,
                            "Top": 0.5638841986656189,
                        },
                        "Polygon": [
                            {"X": 0.5137732625007629, "Y": 0.5639490485191345},
                            {"X": 0.642304539680481, "Y": 0.5638841986656189},
                            {"X": 0.6423131227493286, "Y": 0.5745232105255127},
                            {"X": 0.5137813687324524, "Y": 0.5745878219604492},
                        ],
                    },
                    "Id": "f50b6708-6b7f-42b7-b7d5-49e5b0fbf6c7",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "c316d4a2-6226-47e1-ae46-ec42de583791",
                                "35eeff4a-17d5-41e4-b14d-f419d9bf5dbf",
                                "41c378f3-eb96-4175-be3e-f7033c5cb479",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.10631561279297,
                    "Text": "Niekirk Charles J W *",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1421920210123062,
                            "Height": 0.00894625298678875,
                            "Left": 0.71607905626297,
                            "Top": 0.563790500164032,
                        },
                        "Polygon": [
                            {"X": 0.71607905626297, "Y": 0.5638622641563416},
                            {"X": 0.8582632541656494, "Y": 0.563790500164032},
                            {"X": 0.858271062374115, "Y": 0.5726652145385742},
                            {"X": 0.7160864472389221, "Y": 0.5727367401123047},
                        ],
                    },
                    "Id": "6f3572e7-511a-4cbd-a1e1-32a56446bbd9",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "206483d1-b545-4b04-9789-30512a39e28b",
                                "29333967-a0b1-4dbd-ad57-faad6ff8a63e",
                                "3ce996ec-a2ec-4497-b707-46507c2c837b",
                                "baf67f0a-1ec9-4254-a56c-5575d17c4ff2",
                                "bb272a17-30ff-4f6a-a99f-94adf75f815b",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.87984466552734,
                    "Text": "Alan Francis",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14884743094444275,
                            "Height": 0.01504420954734087,
                            "Left": 0.09938471019268036,
                            "Top": 0.5780068039894104,
                        },
                        "Polygon": [
                            {"X": 0.09938471019268036, "Y": 0.5780816078186035},
                            {"X": 0.24822208285331726, "Y": 0.5780068039894104},
                            {"X": 0.2482321411371231, "Y": 0.5929765701293945},
                            {"X": 0.09939400851726532, "Y": 0.593051016330719},
                        ],
                    },
                    "Id": "7d6fd27e-d9c0-449e-8c36-2c99639f16e1",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "2b224e61-820e-44da-8dbd-ba119229bf48",
                                "58261409-1e35-4807-b8f8-75bec68f64f2",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.02899932861328,
                    "Text": "Borough of Lewisham)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.15047286450862885,
                            "Height": 0.010953251272439957,
                            "Left": 0.5136256217956543,
                            "Top": 0.5761255025863647,
                        },
                        "Polygon": [
                            {"X": 0.5136256217956543, "Y": 0.5762011408805847},
                            {"X": 0.6640896201133728, "Y": 0.5761255025863647},
                            {"X": 0.6640985012054443, "Y": 0.5870033502578735},
                            {"X": 0.5136339664459229, "Y": 0.5870787501335144},
                        ],
                    },
                    "Id": "401014fd-f9ec-4c72-893d-e6bbe278a0d7",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "dde41795-9dc7-45a8-9ff0-c28139bc12e6",
                                "40110550-406b-4468-a5fb-be22c3753d94",
                                "79e81c38-db20-4a12-aa5e-4984be5788c6",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 90.19451141357422,
                    "Text": "Clarke Shannon I **",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1317795068025589,
                            "Height": 0.00891990028321743,
                            "Left": 0.7159947752952576,
                            "Top": 0.5760455131530762,
                        },
                        "Polygon": [
                            {"X": 0.7159947752952576, "Y": 0.5761117935180664},
                            {"X": 0.8477665185928345, "Y": 0.5760455131530762},
                            {"X": 0.8477742671966553, "Y": 0.584899365901947},
                            {"X": 0.7160021662712097, "Y": 0.5849654078483582},
                        ],
                    },
                    "Id": "cf098d77-216c-4352-81db-9ea78ce3e0ee",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "fd5fed05-f5cd-4316-977b-0f454bdb52b8",
                                "c880eb9a-de22-4d00-9fa1-08fce68f2b85",
                                "b7589599-dd47-4ca3-8e68-280cb218a3b6",
                                "742862c5-199f-4512-a710-8cbcabc6a1c8",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.93289947509766,
                    "Text": "QADAR",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09405231475830078,
                            "Height": 0.014996449463069439,
                            "Left": 0.09999311715364456,
                            "Top": 0.6193125247955322,
                        },
                        "Polygon": [
                            {"X": 0.09999311715364456, "Y": 0.6193591952323914},
                            {"X": 0.19403566420078278, "Y": 0.6193125247955322},
                            {"X": 0.19404542446136475, "Y": 0.6342625021934509},
                            {"X": 0.10000240057706833, "Y": 0.6343089938163757},
                        ],
                    },
                    "Id": "d9617636-c18f-4a03-ab62-71050aab692c",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["79210e66-b574-4a00-a329-65402a7a9ea8"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.79671478271484,
                    "Text": "Conservatives",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14849162101745605,
                            "Height": 0.013586771674454212,
                            "Left": 0.29034939408302307,
                            "Top": 0.6308904886245728,
                        },
                        "Polygon": [
                            {"X": 0.29034939408302307, "Y": 0.630963921546936},
                            {"X": 0.43883103132247925, "Y": 0.6308904886245728},
                            {"X": 0.43884098529815674, "Y": 0.6444041132926941},
                            {"X": 0.29035866260528564, "Y": 0.6444772481918335},
                        ],
                    },
                    "Id": "09647b30-44ce-4ca0-9eb1-6390f3432b8e",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["b1be16c0-c2c0-48ba-8192-ab8a055e40e0"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.9334945678711,
                    "Text": "(address in London",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1285654753446579,
                            "Height": 0.010511801578104496,
                            "Left": 0.5137097239494324,
                            "Top": 0.6268847584724426,
                        },
                        "Polygon": [
                            {"X": 0.5137097239494324, "Y": 0.6269484162330627},
                            {"X": 0.6422667503356934, "Y": 0.6268847584724426},
                            {"X": 0.6422752141952515, "Y": 0.6373330950737},
                            {"X": 0.5137177109718323, "Y": 0.6373965740203857},
                        ],
                    },
                    "Id": "6cdebb37-e4b1-4b77-912d-de8b032f9309",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "c2f4faa8-7907-4a5b-abc6-f7219428b9ab",
                                "0197fe23-9303-4359-880a-31951e038327",
                                "76b4371b-038f-4b4a-8159-65c709586388",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.75881958007812,
                    "Text": "Qazi Abdul Q",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09011168032884598,
                            "Height": 0.008963914588093758,
                            "Left": 0.7161157727241516,
                            "Top": 0.6268413066864014,
                        },
                        "Polygon": [
                            {"X": 0.7161157727241516, "Y": 0.6268858909606934},
                            {"X": 0.806219756603241, "Y": 0.6268413066864014},
                            {"X": 0.806227445602417, "Y": 0.6357607245445251},
                            {"X": 0.7161232233047485, "Y": 0.6358051896095276},
                        ],
                    },
                    "Id": "62df2d7a-098b-494e-94cd-668d422eac5c",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "7083f705-4e01-4545-8d72-974ad153be03",
                                "0f7020d8-e291-4ad6-9dc4-6d22406b3cc6",
                                "803981a7-5025-41cc-89b3-d12e67a0ae82",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 97.66498565673828,
                    "Text": "*",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0053612831979990005,
                            "Height": 0.004342852625995874,
                            "Left": 0.8103842735290527,
                            "Top": 0.626857578754425,
                        },
                        "Polygon": [
                            {"X": 0.8103842735290527, "Y": 0.6268602013587952},
                            {"X": 0.8157418370246887, "Y": 0.626857578754425},
                            {"X": 0.8157455921173096, "Y": 0.6311977505683899},
                            {"X": 0.8103880882263184, "Y": 0.6312004327774048},
                        ],
                    },
                    "Id": "5ce8f47c-22a8-43c2-91af-b7a5f65c2ab4",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["65c94d2c-caa4-4c9b-b8e3-4f2c46ed9f5b"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.29061889648438,
                    "Text": "Siama",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07505691051483154,
                            "Height": 0.015140949748456478,
                            "Left": 0.10013869404792786,
                            "Top": 0.6411055326461792,
                        },
                        "Polygon": [
                            {"X": 0.10013869404792786, "Y": 0.6411425471305847},
                            {"X": 0.17518582940101624, "Y": 0.6411055326461792},
                            {"X": 0.1751956045627594, "Y": 0.6562096476554871},
                            {"X": 0.10014807432889938, "Y": 0.6562464833259583},
                        ],
                    },
                    "Id": "bd0a10a5-ff47-431d-88a1-b3b23849bfe7",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["393d9dff-f936-47d7-97aa-ffc099bf1a8a"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 98.51121520996094,
                    "Text": "Borough of Lewisham)",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.15079368650913239,
                            "Height": 0.011013776063919067,
                            "Left": 0.5135374069213867,
                            "Top": 0.6389728784561157,
                        },
                        "Polygon": [
                            {"X": 0.5135374069213867, "Y": 0.6390472650527954},
                            {"X": 0.6643221974372864, "Y": 0.6389728784561157},
                            {"X": 0.6643311381340027, "Y": 0.6499124765396118},
                            {"X": 0.5135457515716553, "Y": 0.6499866247177124},
                        ],
                    },
                    "Id": "3dde21f5-f787-42e9-a40b-ef83c97cdb53",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "d56315c6-74a4-4cb5-a1a2-52f0b72a748f",
                                "3d0d7278-1d72-4908-9b75-4fae04f1a6c5",
                                "801bed18-c8b4-43a6-ad46-e4826cff45d2",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.6759262084961,
                    "Text": "Baksi Nikolas",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09019874781370163,
                            "Height": 0.008781886659562588,
                            "Left": 0.716232419013977,
                            "Top": 0.6391857862472534,
                        },
                        "Polygon": [
                            {"X": 0.716232419013977, "Y": 0.6392303109169006},
                            {"X": 0.8064236044883728, "Y": 0.6391857862472534},
                            {"X": 0.8064311742782593, "Y": 0.6479232907295227},
                            {"X": 0.7162396907806396, "Y": 0.6479676961898804},
                        ],
                    },
                    "Id": "cb3492ff-3ad7-4eda-9005-3307ea319b1a",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "8311ac0b-cdb9-4cdd-8287-229107084207",
                                "5364dddf-4a73-4370-be4c-deeea65e56a6",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 88.31393432617188,
                    "Text": "**",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.011022998951375484,
                            "Height": 0.003929123282432556,
                            "Left": 0.8110170960426331,
                            "Top": 0.6392341256141663,
                        },
                        "Polygon": [
                            {"X": 0.8110170960426331, "Y": 0.6392395496368408},
                            {"X": 0.8220366835594177, "Y": 0.6392341256141663},
                            {"X": 0.8220401406288147, "Y": 0.6431578397750854},
                            {"X": 0.8110204935073853, "Y": 0.64316326379776},
                        ],
                    },
                    "Id": "40936e43-27f1-4c55-9ec3-2143741f4ff3",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": ["bf261c7a-5e43-4138-b994-c8b5019eff48"],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.94667053222656,
                    "Text": "The persons above stand validly nominated in the Deptford By-election with a poll to",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.8755677938461304,
                            "Height": 0.017481617629528046,
                            "Left": 0.05939551070332527,
                            "Top": 0.6855397820472717,
                        },
                        "Polygon": [
                            {"X": 0.05939551070332527, "Y": 0.6859657168388367},
                            {"X": 0.9349477887153625, "Y": 0.6855397820472717},
                            {"X": 0.9349632859230042, "Y": 0.7025976777076721},
                            {"X": 0.0594058632850647, "Y": 0.7030214071273804},
                        ],
                    },
                    "Id": "f35529e4-1f89-4578-b8b1-aefcae596150",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "64e5d69c-860e-47df-b5fa-96b81f78891a",
                                "2ab75076-b6c6-4c03-bf27-4fa638abb9cf",
                                "8f2556f6-33fe-478e-96e1-1b28a623c762",
                                "a7049f7e-c590-41f8-825c-89bf5ea4e194",
                                "f3dd540a-720e-4449-aad6-87810fb0c3ed",
                                "24502c61-7933-4e15-847c-95417715a559",
                                "3489a51e-54eb-4fac-955b-0d6920060c65",
                                "e6ff8255-d23e-46da-bb36-db59be757d6a",
                                "92e1adfa-c526-4a77-b975-3e61dd462447",
                                "d259edc0-7902-42dc-96f0-c25e49d7b07b",
                                "b5bf66b1-4719-44ee-8e92-7d838e0542a6",
                                "e602b286-17cb-4d60-890e-525775711a5c",
                                "936fc403-f279-4e6d-bc95-9e112da3d5f7",
                                "f599f9cf-d136-4bf0-99db-a2ac608e743c",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.40859985351562,
                    "Text": "be held on Thursday 9 November, from 7am to 10pm.",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.5723395347595215,
                            "Height": 0.016784077510237694,
                            "Left": 0.060459405183792114,
                            "Top": 0.7050212621688843,
                        },
                        "Polygon": [
                            {
                                "X": 0.060459405183792114,
                                "Y": 0.7052980661392212,
                            },
                            {"X": 0.6327856183052063, "Y": 0.7050212621688843},
                            {"X": 0.6327989101409912, "Y": 0.7215299606323242},
                            {
                                "X": 0.060469429939985275,
                                "Y": 0.7218053340911865,
                            },
                        ],
                    },
                    "Id": "1f5503e8-955b-44de-bb53-b1cfd9791bde",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "81fc0038-f432-4eac-840d-a9f170b3f4e1",
                                "e79b13a9-0dd3-47ad-ba67-84e1392cb151",
                                "571f3dfb-f819-498d-b996-59ce3a70408e",
                                "58b78454-bbcb-43b7-bed1-755328f08704",
                                "00ae46e1-b874-4918-bd56-8e3ecea93730",
                                "64ab6b41-6732-47f4-bee3-88e582a2564a",
                                "470ae60a-b252-41cb-946f-fe8dec9156e5",
                                "0d569fd5-2514-4d73-b59a-0162ece007d5",
                                "88b6c374-55eb-426a-8618-c89d6c4850e5",
                                "573d940c-fc64-47c3-8955-d34c39fe2e7e",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.97879028320312,
                    "Text": "Dated Monday 16 October 2023",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.3334278464317322,
                            "Height": 0.016779784113168716,
                            "Left": 0.06110624223947525,
                            "Top": 0.9093807935714722,
                        },
                        "Polygon": [
                            {"X": 0.06110624223947525, "Y": 0.9095318913459778},
                            {"X": 0.3945220708847046, "Y": 0.9093807935714722},
                            {"X": 0.3945341110229492, "Y": 0.926010251045227},
                            {"X": 0.06111634522676468, "Y": 0.9261605739593506},
                        ],
                    },
                    "Id": "f1415a15-ac5f-495d-b0c3-f57afb4351a0",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "728b5d2f-2373-445f-a206-e83a65ffcb18",
                                "d5c55ef7-037c-466c-b956-138875c316c0",
                                "f681e108-cdc7-40d5-b506-98018ce6c742",
                                "5678b13f-0f2f-4756-8df4-7c6e7fa5792f",
                                "85dffc5a-2c30-48e8-b9cb-333588886952",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.87670135498047,
                    "Text": "Jennifer Daothong",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.19196133315563202,
                            "Height": 0.01672041043639183,
                            "Left": 0.7044742703437805,
                            "Top": 0.9095743894577026,
                        },
                        "Polygon": [
                            {"X": 0.7044742703437805, "Y": 0.9096614122390747},
                            {"X": 0.8964206576347351, "Y": 0.9095743894577026},
                            {"X": 0.8964356184005737, "Y": 0.9262083172798157},
                            {"X": 0.7044880986213684, "Y": 0.9262948036193848},
                        ],
                    },
                    "Id": "b5fef35f-2e36-44f1-919a-1235a4bbac43",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "a2f29f81-c89d-4bca-b65f-f54e224bff5a",
                                "e3565e3f-b539-45d3-b24a-137c7cc9e7d1",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.97277069091797,
                    "Text": "Returning Officer",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.17696207761764526,
                            "Height": 0.016588138416409492,
                            "Left": 0.7201766967773438,
                            "Top": 0.928695559501648,
                        },
                        "Polygon": [
                            {"X": 0.7201766967773438, "Y": 0.9287753105163574},
                            {"X": 0.8971239328384399, "Y": 0.928695559501648},
                            {"X": 0.897138774394989, "Y": 0.9452044367790222},
                            {"X": 0.7201904654502869, "Y": 0.9452837109565735},
                        ],
                    },
                    "Id": "3b25330f-5518-4f0b-8de6-e9a9dc37d751",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "21b02bee-df70-44bb-82a9-fe870871ffd3",
                                "2d4bbbb1-a2cb-4855-a269-fc51120b5cda",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "LINE",
                    "Confidence": 99.46063232421875,
                    "Text": "Printed and published by the Returning Officer, Ground Floor, Laurence House, Catford, London, SE6 4RU",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.6353176832199097,
                            "Height": 0.01023896411061287,
                            "Left": 0.18190975487232208,
                            "Top": 0.9654234051704407,
                        },
                        "Polygon": [
                            {"X": 0.18190975487232208, "Y": 0.9657061100006104},
                            {"X": 0.8172187805175781, "Y": 0.9654234051704407},
                            {"X": 0.8172274231910706, "Y": 0.9753806591033936},
                            {"X": 0.1819162219762802, "Y": 0.9756624102592468},
                        ],
                    },
                    "Id": "bfb9cb24-3d8f-4800-9bab-fe8786183e36",
                    "Relationships": [
                        {
                            "Type": "CHILD",
                            "Ids": [
                                "bd84b4c2-2101-4583-b26a-c20b19d5be88",
                                "ca3c5440-61e6-4404-b38d-8c3b898cbc00",
                                "c26939ce-b606-426f-a33b-bb31a840c27a",
                                "e195cc68-1355-4975-95c2-766f26963800",
                                "b8654b64-189a-4954-898d-f9c8edee9c8d",
                                "9d0312ff-f743-47d2-9107-d840f76a362e",
                                "55e522a6-848c-4aa5-94c8-fc3532f464f6",
                                "77812498-fe7d-47ee-8855-7c750214948c",
                                "92ace678-ce10-4b00-aac0-05f362479b64",
                                "9729c48e-8197-49c0-9c86-97a20ce12e6a",
                                "277107d2-8266-471d-a575-c726c7a190f1",
                                "4ca33f52-9d02-4631-b770-30305278cbe4",
                                "0fcc9633-8319-4aee-9ad6-af62f6a1d0db",
                                "79ee1c09-6875-45cb-a3df-7ea7dbbd0cdb",
                                "61e54dce-a241-4eff-93e2-6fc38e3a021e",
                            ],
                        }
                    ],
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96259307861328,
                    "Text": "STATEMENT",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.3673827648162842,
                            "Height": 0.033109404146671295,
                            "Left": 0.11023642122745514,
                            "Top": 0.04111818969249725,
                        },
                        "Polygon": [
                            {
                                "X": 0.11023642122745514,
                                "Y": 0.04133205860853195,
                            },
                            {"X": 0.4775944650173187, "Y": 0.04111818969249725},
                            {"X": 0.4776192009449005, "Y": 0.07401551306247711},
                            {
                                "X": 0.11025696992874146,
                                "Y": 0.07422759383916855,
                            },
                        ],
                    },
                    "Id": "49a7823b-f1ec-4297-91fb-199a0452ab7d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98768615722656,
                    "Text": "OF",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08051542937755585,
                            "Height": 0.032791391015052795,
                            "Left": 0.4963679611682892,
                            "Top": 0.041402172297239304,
                        },
                        "Polygon": [
                            {"X": 0.4963679611682892, "Y": 0.04144902899861336},
                            {
                                "X": 0.5768576264381409,
                                "Y": 0.041402172297239304,
                            },
                            {"X": 0.5768833756446838, "Y": 0.07414709776639938},
                            {"X": 0.4963928163051605, "Y": 0.0741935595870018},
                        ],
                    },
                    "Id": "4bd8e7b9-8173-47f9-b416-65f7cef7dd84",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94049835205078,
                    "Text": "PERSONS",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.29245948791503906,
                            "Height": 0.03371758013963699,
                            "Left": 0.5981320142745972,
                            "Top": 0.04087038338184357,
                        },
                        "Polygon": [
                            {
                                "X": 0.5981320142745972,
                                "Y": 0.041040629148483276,
                            },
                            {"X": 0.8905614614486694, "Y": 0.04087038338184357},
                            {"X": 0.8905915021896362, "Y": 0.07441917061805725},
                            {"X": 0.5981586575508118, "Y": 0.07458796352148056},
                        ],
                    },
                    "Id": "80397ad2-5d48-4b7d-a9e4-6c9ff93d80ac",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92805480957031,
                    "Text": "NOMINATED",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.36702030897140503,
                            "Height": 0.03284572437405586,
                            "Left": 0.3171496093273163,
                            "Top": 0.09061070531606674,
                        },
                        "Polygon": [
                            {"X": 0.3171496093273163, "Y": 0.09082166105508804},
                            {"X": 0.68414306640625, "Y": 0.09061070531606674},
                            {"X": 0.6841699481010437, "Y": 0.12324725091457367},
                            {"X": 0.3171723484992981, "Y": 0.1234564334154129},
                        ],
                    },
                    "Id": "c4e02eaa-b43e-4500-91ab-7bd812fd1933",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.95448303222656,
                    "Text": "London",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.10890500247478485,
                            "Height": 0.01685975305736065,
                            "Left": 0.28295084834098816,
                            "Top": 0.14740543067455292,
                        },
                        "Polygon": [
                            {
                                "X": 0.28295084834098816,
                                "Y": 0.14746710658073425,
                            },
                            {"X": 0.3918437063694, "Y": 0.14740543067455292},
                            {"X": 0.3918558359146118, "Y": 0.16420377790927887},
                            {"X": 0.2829623222351074, "Y": 0.16426518559455872},
                        ],
                    },
                    "Id": "3f6c0814-cac0-4d56-a486-7056cdd8e91d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97550964355469,
                    "Text": "Borough",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1238669753074646,
                            "Height": 0.02136540785431862,
                            "Left": 0.4022396504878998,
                            "Top": 0.1474420130252838,
                        },
                        "Polygon": [
                            {"X": 0.4022396504878998, "Y": 0.14751216769218445},
                            {"X": 0.5260902643203735, "Y": 0.1474420130252838},
                            {"X": 0.5261066555976868, "Y": 0.16873766481876373},
                            {"X": 0.402255117893219, "Y": 0.16880743205547333},
                        ],
                    },
                    "Id": "27191b33-9616-4965-98c9-22f626b45b42",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.978759765625,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.02824215777218342,
                            "Height": 0.016907544806599617,
                            "Left": 0.5356388688087463,
                            "Top": 0.14744386076927185,
                        },
                        "Polygon": [
                            {"X": 0.5356388688087463, "Y": 0.14745984971523285},
                            {"X": 0.5638678073883057, "Y": 0.14744386076927185},
                            {"X": 0.563880980014801, "Y": 0.1643354892730713},
                            {"X": 0.5356518626213074, "Y": 0.16435140371322632},
                        ],
                    },
                    "Id": "c7290639-f2bd-42ff-a6a8-ab3ccfc0a81c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94554138183594,
                    "Text": "Lewisham",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14347441494464874,
                            "Height": 0.016783345490694046,
                            "Left": 0.5739517211914062,
                            "Top": 0.14743395149707794,
                        },
                        "Polygon": [
                            {"X": 0.5739517211914062, "Y": 0.147515207529068},
                            {"X": 0.7174121737480164, "Y": 0.14743395149707794},
                            {"X": 0.7174261212348938, "Y": 0.1641363948583603},
                            {"X": 0.5739648342132568, "Y": 0.1642172932624817},
                        ],
                    },
                    "Id": "49bda281-4097-4879-a826-0d6f47d90c97",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96074676513672,
                    "Text": "Election",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.22791257500648499,
                            "Height": 0.033763982355594635,
                            "Left": 0.16627052426338196,
                            "Top": 0.18837574124336243,
                        },
                        "Polygon": [
                            {"X": 0.16627052426338196, "Y": 0.1885034292936325},
                            {"X": 0.3941587805747986, "Y": 0.18837574124336243},
                            {
                                "X": 0.39418309926986694,
                                "Y": 0.22201316058635712,
                            },
                            {"X": 0.1662921905517578, "Y": 0.22213971614837646},
                        ],
                    },
                    "Id": "26587598-2085-4046-be81-df48ac455c21",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98978424072266,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05498144030570984,
                            "Height": 0.03250570595264435,
                            "Left": 0.41505166888237,
                            "Top": 0.18910427391529083,
                        },
                        "Polygon": [
                            {"X": 0.41505166888237, "Y": 0.18913505971431732},
                            {"X": 0.4700087904930115, "Y": 0.18910427391529083},
                            {"X": 0.47003310918807983, "Y": 0.221579447388649},
                            {"X": 0.4150753915309906, "Y": 0.22160997986793518},
                        ],
                    },
                    "Id": "4715d5d4-8596-43c8-8dea-4b19d5029d29",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97660827636719,
                    "Text": "a",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03061436116695404,
                            "Height": 0.024623319506645203,
                            "Left": 0.4888189435005188,
                            "Top": 0.19678017497062683,
                        },
                        "Polygon": [
                            {"X": 0.4888189435005188, "Y": 0.19679728150367737},
                            {"X": 0.5194144248962402, "Y": 0.19678017497062683},
                            {"X": 0.519433319568634, "Y": 0.22138650715351105},
                            {"X": 0.4888375401496887, "Y": 0.22140349447727203},
                        ],
                    },
                    "Id": "fb344ff5-8e59-4000-8c83-3102199cd778",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.78252410888672,
                    "Text": "Councillor",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.29644203186035156,
                            "Height": 0.03337438777089119,
                            "Left": 0.5403520464897156,
                            "Top": 0.18850156664848328,
                        },
                        "Polygon": [
                            {"X": 0.5403520464897156, "Y": 0.1886676400899887},
                            {"X": 0.8367649912834167, "Y": 0.18850156664848328},
                            {"X": 0.8367940783500671, "Y": 0.22171133756637573},
                            {"X": 0.5403777360916138, "Y": 0.22187595069408417},
                        ],
                    },
                    "Id": "6fadb6e2-cb46-4854-93fe-a40daea8e8c5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99202728271484,
                    "Text": "The",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04050346463918686,
                            "Height": 0.013198397122323513,
                            "Left": 0.09331551194190979,
                            "Top": 0.2450951635837555,
                        },
                        "Polygon": [
                            {
                                "X": 0.09331551194190979,
                                "Y": 0.24511751532554626,
                            },
                            {"X": 0.1338106393814087, "Y": 0.2450951635837555},
                            {"X": 0.13381896913051605, "Y": 0.2582712769508362},
                            {"X": 0.09332366287708282, "Y": 0.2582935690879822},
                        ],
                    },
                    "Id": "29ac063b-a32c-4741-bcdb-1436e6e513ad",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99054718017578,
                    "Text": "following",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09172619134187698,
                            "Height": 0.017055293545126915,
                            "Left": 0.14051896333694458,
                            "Top": 0.24481071531772614,
                        },
                        "Polygon": [
                            {
                                "X": 0.14051896333694458,
                                "Y": 0.24486133456230164,
                            },
                            {
                                "X": 0.23223382234573364,
                                "Y": 0.24481071531772614,
                            },
                            {"X": 0.23224516212940216, "Y": 0.26181560754776},
                            {"X": 0.14052976667881012, "Y": 0.2618660032749176},
                        ],
                    },
                    "Id": "506e1bde-a82d-4b9a-8092-883dcb16561c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98491668701172,
                    "Text": "is",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.01641358807682991,
                            "Height": 0.01302203256636858,
                            "Left": 0.23926711082458496,
                            "Top": 0.24514535069465637,
                        },
                        "Polygon": [
                            {
                                "X": 0.23926711082458496,
                                "Y": 0.24515439569950104,
                            },
                            {"X": 0.2556719183921814, "Y": 0.24514535069465637},
                            {"X": 0.2556806802749634, "Y": 0.2581583559513092},
                            {"X": 0.23927581310272217, "Y": 0.2581673860549927},
                        ],
                    },
                    "Id": "abd22fbb-0a26-4e5e-861f-108f08e5a2c0",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9714584350586,
                    "Text": "a",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.012846291065216064,
                            "Height": 0.010229512117803097,
                            "Left": 0.26262372732162476,
                            "Top": 0.24811455607414246,
                        },
                        "Polygon": [
                            {
                                "X": 0.26262372732162476,
                                "Y": 0.24812163412570953,
                            },
                            {"X": 0.2754630744457245, "Y": 0.24811455607414246},
                            {"X": 0.2754700183868408, "Y": 0.25833702087402344},
                            {"X": 0.2626306712627411, "Y": 0.25834405422210693},
                        ],
                    },
                    "Id": "73144b29-b016-4829-8b12-c27793fa7f68",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98303985595703,
                    "Text": "statement",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1032300591468811,
                            "Height": 0.012437700293958187,
                            "Left": 0.28253912925720215,
                            "Top": 0.2459055781364441,
                        },
                        "Polygon": [
                            {
                                "X": 0.28253912925720215,
                                "Y": 0.24596253037452698,
                            },
                            {"X": 0.38576027750968933, "Y": 0.2459055781364441},
                            {"X": 0.38576918840408325, "Y": 0.2582865059375763},
                            {
                                "X": 0.28254759311676025,
                                "Y": 0.25834327936172485,
                            },
                        ],
                    },
                    "Id": "80a5659b-aa3a-4141-9bb8-7d4a88bd3401",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99529266357422,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.019852150231599808,
                            "Height": 0.012939696200191975,
                            "Left": 0.3920035660266876,
                            "Top": 0.24508291482925415,
                        },
                        "Polygon": [
                            {"X": 0.3920035660266876, "Y": 0.24509385228157043},
                            {"X": 0.4118463099002838, "Y": 0.24508291482925415},
                            {"X": 0.4118557274341583, "Y": 0.25801169872283936},
                            {
                                "X": 0.39201292395591736,
                                "Y": 0.25802260637283325,
                            },
                        ],
                    },
                    "Id": "3c4922ef-c194-4de3-81e3-9c2db62b6dc8",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99710845947266,
                    "Text": "the",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03248349204659462,
                            "Height": 0.01284237951040268,
                            "Left": 0.4176347851753235,
                            "Top": 0.24528130888938904,
                        },
                        "Polygon": [
                            {"X": 0.4176347851753235, "Y": 0.24529923498630524},
                            {
                                "X": 0.45010876655578613,
                                "Y": 0.24528130888938904,
                            },
                            {"X": 0.4501182734966278, "Y": 0.2581058442592621},
                            {"X": 0.4176441729068756, "Y": 0.2581236958503723},
                        ],
                    },
                    "Id": "0a00517b-2e73-460d-9aea-6c2adc63fdb7",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98751068115234,
                    "Text": "persons",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0823296532034874,
                            "Height": 0.013052471913397312,
                            "Left": 0.4578682780265808,
                            "Top": 0.24804244935512543,
                        },
                        "Polygon": [
                            {"X": 0.4578682780265808, "Y": 0.2480878382921219},
                            {"X": 0.5401878952980042, "Y": 0.24804244935512543},
                            {"X": 0.5401979088783264, "Y": 0.26104968786239624},
                            {"X": 0.4578779637813568, "Y": 0.26109492778778076},
                        ],
                    },
                    "Id": "dedf2347-f72b-48bc-8772-cb8d1d842da8",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97815704345703,
                    "Text": "nominated",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.10829806327819824,
                            "Height": 0.01284222211688757,
                            "Left": 0.5482285022735596,
                            "Top": 0.24532058835029602,
                        },
                        "Polygon": [
                            {"X": 0.5482285022735596, "Y": 0.24538034200668335},
                            {"X": 0.6565161347389221, "Y": 0.24532058835029602},
                            {"X": 0.6565265655517578, "Y": 0.25810325145721436},
                            {"X": 0.5482383966445923, "Y": 0.25816279649734497},
                        ],
                    },
                    "Id": "06948c35-9ce5-44ec-a296-56356e891085",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99806213378906,
                    "Text": "for",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.02790634147822857,
                            "Height": 0.013054296374320984,
                            "Left": 0.6634809374809265,
                            "Top": 0.24497924745082855,
                        },
                        "Polygon": [
                            {"X": 0.6634809374809265, "Y": 0.2449946403503418},
                            {"X": 0.6913765072822571, "Y": 0.24497924745082855},
                            {"X": 0.6913872957229614, "Y": 0.2580181956291199},
                            {"X": 0.6634916067123413, "Y": 0.25803354382514954},
                        ],
                    },
                    "Id": "ce059fd9-97ea-48c5-8041-d0b65c2c9e53",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98023223876953,
                    "Text": "election",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0807226151227951,
                            "Height": 0.0132204694673419,
                            "Left": 0.697303295135498,
                            "Top": 0.24506978690624237,
                        },
                        "Polygon": [
                            {"X": 0.697303295135498, "Y": 0.24511434137821198},
                            {"X": 0.7780146598815918, "Y": 0.24506978690624237},
                            {"X": 0.7780259251594543, "Y": 0.25824588537216187},
                            {"X": 0.6973142027854919, "Y": 0.25829026103019714},
                        ],
                    },
                    "Id": "857acd3e-8731-4a93-a461-8b26af676c9c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9867935180664,
                    "Text": "as",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.024146735668182373,
                            "Height": 0.010131296701729298,
                            "Left": 0.7855104804039001,
                            "Top": 0.24809424579143524,
                        },
                        "Polygon": [
                            {"X": 0.7855104804039001, "Y": 0.24810756742954254},
                            {"X": 0.8096484541893005, "Y": 0.24809424579143524},
                            {"X": 0.8096572160720825, "Y": 0.25821226835250854},
                            {"X": 0.7855191826820374, "Y": 0.25822556018829346},
                        ],
                    },
                    "Id": "6089051b-80bc-443c-907a-9307115a109a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97299194335938,
                    "Text": "Borough",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08751083165407181,
                            "Height": 0.016417240723967552,
                            "Left": 0.8170388340950012,
                            "Top": 0.24518898129463196,
                        },
                        "Polygon": [
                            {"X": 0.8170388340950012, "Y": 0.24523727595806122},
                            {"X": 0.9045349359512329, "Y": 0.24518898129463196},
                            {"X": 0.9045496582984924, "Y": 0.2615581452846527},
                            {"X": 0.8170530200004578, "Y": 0.26160621643066406},
                        ],
                    },
                    "Id": "e806155c-b17d-4478-ba27-64d8731d8186",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.8800277709961,
                    "Text": "Councillor",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.10476983338594437,
                            "Height": 0.013450127094984055,
                            "Left": 0.43105176091194153,
                            "Top": 0.2638612687587738,
                        },
                        "Polygon": [
                            {
                                "X": 0.43105176091194153,
                                "Y": 0.26391878724098206,
                            },
                            {"X": 0.5358112454414368, "Y": 0.2638612687587738},
                            {"X": 0.5358216166496277, "Y": 0.2772540748119354},
                            {
                                "X": 0.43106162548065186,
                                "Y": 0.27731138467788696,
                            },
                        ],
                    },
                    "Id": "f9fc4e14-6e9e-4fd6-9cf4-994fe4aef56d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99685668945312,
                    "Text": "for",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.028275422751903534,
                            "Height": 0.013148680329322815,
                            "Left": 0.5412158966064453,
                            "Top": 0.26400434970855713,
                        },
                        "Polygon": [
                            {"X": 0.5412158966064453, "Y": 0.2640198767185211},
                            {"X": 0.5694810152053833, "Y": 0.26400434970855713},
                            {"X": 0.5694913268089294, "Y": 0.2771375775337219},
                            {"X": 0.5412260890007019, "Y": 0.27715304493904114},
                        ],
                    },
                    "Id": "38636179-86af-44c2-abe1-c7fbb33ad891",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92713928222656,
                    "Text": "Deptford",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.24436597526073456,
                            "Height": 0.04146783798933029,
                            "Left": 0.29390066862106323,
                            "Top": 0.3007989227771759,
                        },
                        "Polygon": [
                            {
                                "X": 0.29390066862106323,
                                "Y": 0.30093175172805786,
                            },
                            {"X": 0.5382347106933594, "Y": 0.3007989227771759},
                            {"X": 0.538266658782959, "Y": 0.3421354293823242},
                            {"X": 0.2939291298389435, "Y": 0.3422667384147644},
                        ],
                    },
                    "Id": "a7e4229a-909d-4c24-9cd1-d89f4f855d56",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.988525390625,
                    "Text": "Ward",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1489720195531845,
                            "Height": 0.03250165283679962,
                            "Left": 0.5582439303398132,
                            "Top": 0.30120283365249634,
                        },
                        "Polygon": [
                            {"X": 0.5582439303398132, "Y": 0.3012838065624237},
                            {"X": 0.7071889638900757, "Y": 0.30120283365249634},
                            {"X": 0.7072159647941589, "Y": 0.3336242437362671},
                            {"X": 0.558269202709198, "Y": 0.33370447158813477},
                        ],
                    },
                    "Id": "44145c2a-aaf7-4303-9c31-ddecfb452941",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96981811523438,
                    "Text": "Name",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.054184697568416595,
                            "Height": 0.011320019140839577,
                            "Left": 0.09993820637464523,
                            "Top": 0.3709922730922699,
                        },
                        "Polygon": [
                            {"X": 0.09993820637464523, "Y": 0.3710211515426636},
                            {"X": 0.1541156768798828, "Y": 0.3709922730922699},
                            {"X": 0.15412290394306183, "Y": 0.382283478975296},
                            {"X": 0.09994521737098694, "Y": 0.3823122978210449},
                        ],
                    },
                    "Id": "a9f9e43f-7609-455b-ad04-07ed57a4cb65",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.95362091064453,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.019435761496424675,
                            "Height": 0.011361569166183472,
                            "Left": 0.15999038517475128,
                            "Top": 0.37091970443725586,
                        },
                        "Polygon": [
                            {"X": 0.15999038517475128, "Y": 0.3709300458431244},
                            {
                                "X": 0.17941878736019135,
                                "Y": 0.37091970443725586,
                            },
                            {"X": 0.1794261485338211, "Y": 0.3822709321975708},
                            {
                                "X": 0.15999767184257507,
                                "Y": 0.38228127360343933,
                            },
                        ],
                    },
                    "Id": "8ce5fe8e-40e6-49ee-a94e-f8cb11bb1772",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92391204833984,
                    "Text": "Description",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.11043643206357956,
                            "Height": 0.014214947819709778,
                            "Left": 0.2903299331665039,
                            "Top": 0.37070953845977783,
                        },
                        "Polygon": [
                            {"X": 0.2903299331665039, "Y": 0.3707684278488159},
                            {"X": 0.4007561206817627, "Y": 0.37070953845977783},
                            {"X": 0.40076637268066406, "Y": 0.3848658502101898},
                            {"X": 0.2903396785259247, "Y": 0.3849245011806488},
                        ],
                    },
                    "Id": "242f76e7-5def-49a6-a2f6-4ab5243be636",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.95148468017578,
                    "Text": "Home",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.055341221392154694,
                            "Height": 0.011410586535930634,
                            "Left": 0.5137354731559753,
                            "Top": 0.3792106807231903,
                        },
                        "Polygon": [
                            {"X": 0.5137354731559753, "Y": 0.37924012541770935},
                            {"X": 0.5690677762031555, "Y": 0.3792106807231903},
                            {"X": 0.569076657295227, "Y": 0.39059191942214966},
                            {"X": 0.5137441754341125, "Y": 0.39062127470970154},
                        ],
                    },
                    "Id": "234e99b5-8bf4-4526-9a02-1549d1fe03f7",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98082733154297,
                    "Text": "Address",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08118367940187454,
                            "Height": 0.011540534906089306,
                            "Left": 0.574320375919342,
                            "Top": 0.3791722059249878,
                        },
                        "Polygon": [
                            {"X": 0.574320375919342, "Y": 0.37921538949012756},
                            {"X": 0.6554946899414062, "Y": 0.3791722059249878},
                            {"X": 0.655504047870636, "Y": 0.39066970348358154},
                            {"X": 0.5743293762207031, "Y": 0.3907127380371094},
                        ],
                    },
                    "Id": "be277113-f9df-483f-b9be-e310461400a6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92527770996094,
                    "Text": "Proposer",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08796270191669464,
                            "Height": 0.013993156142532825,
                            "Left": 0.7166522741317749,
                            "Top": 0.37097036838531494,
                        },
                        "Polygon": [
                            {"X": 0.7166522741317749, "Y": 0.3710172474384308},
                            {"X": 0.804602861404419, "Y": 0.37097036838531494},
                            {"X": 0.8046149611473083, "Y": 0.3849168121814728},
                            {"X": 0.7166638970375061, "Y": 0.3849635124206543},
                        ],
                    },
                    "Id": "bffcbf83-fc0a-4e56-ab69-abcf8746c60d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.76261138916016,
                    "Text": "(*)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0209775660187006,
                            "Height": 0.014116126112639904,
                            "Left": 0.8102051019668579,
                            "Top": 0.37069186568260193,
                        },
                        "Polygon": [
                            {"X": 0.8102051019668579, "Y": 0.3707030415534973},
                            {"X": 0.831170380115509, "Y": 0.37069186568260193},
                            {"X": 0.8311827182769775, "Y": 0.3847968578338623},
                            {"X": 0.8102173805236816, "Y": 0.3848080039024353},
                        ],
                    },
                    "Id": "f86a7008-8399-463c-98b8-3ce5568392cc",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9234390258789,
                    "Text": "Candidate",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09670990705490112,
                            "Height": 0.01165726874023676,
                            "Left": 0.09970410913228989,
                            "Top": 0.3870118260383606,
                        },
                        "Polygon": [
                            {"X": 0.09970410913228989, "Y": 0.3870631754398346},
                            {"X": 0.19640642404556274, "Y": 0.3870118260383606},
                            {"X": 0.1964140087366104, "Y": 0.3986179232597351},
                            {"X": 0.09971132129430771, "Y": 0.3986690938472748},
                        ],
                    },
                    "Id": "5e590528-70c2-45d1-bdf4-ff7f6f714c5d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.91242980957031,
                    "Text": "(if",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.018841098994016647,
                            "Height": 0.014222084544599056,
                            "Left": 0.2903864085674286,
                            "Top": 0.3869141638278961,
                        },
                        "Polygon": [
                            {"X": 0.2903864085674286, "Y": 0.386924147605896},
                            {"X": 0.3092176616191864, "Y": 0.3869141638278961},
                            {
                                "X": 0.30922752618789673,
                                "Y": 0.40112629532814026,
                            },
                            {
                                "X": 0.29039618372917175,
                                "Y": 0.40113624930381775,
                            },
                        ],
                    },
                    "Id": "580803c9-819f-4f6e-bcdb-e7de5019e7ff",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9603500366211,
                    "Text": "any)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.041153062134981155,
                            "Height": 0.014148508198559284,
                            "Left": 0.3145098090171814,
                            "Top": 0.3871407210826874,
                        },
                        "Polygon": [
                            {"X": 0.3145098090171814, "Y": 0.38716256618499756},
                            {"X": 0.3556528389453888, "Y": 0.3871407210826874},
                            {
                                "X": 0.35566285252571106,
                                "Y": 0.40126746892929077,
                            },
                            {"X": 0.31451961398124695, "Y": 0.4012892246246338},
                        ],
                    },
                    "Id": "7ea780e7-92a5-427e-89f3-0dc549ecb461",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94164276123047,
                    "Text": "Seconder",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0922020822763443,
                            "Height": 0.011568216606974602,
                            "Left": 0.716191291809082,
                            "Top": 0.38698098063468933,
                        },
                        "Polygon": [
                            {"X": 0.716191291809082, "Y": 0.3870299160480499},
                            {"X": 0.8083834052085876, "Y": 0.38698098063468933},
                            {"X": 0.8083933591842651, "Y": 0.3985004127025604},
                            {"X": 0.7162009477615356, "Y": 0.3985491991043091},
                        ],
                    },
                    "Id": "53b78b39-8da4-4882-8d97-08e2566cba2b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.4502944946289,
                    "Text": "(**)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.02861512079834938,
                            "Height": 0.014580188319087029,
                            "Left": 0.8141839504241943,
                            "Top": 0.3868173062801361,
                        },
                        "Polygon": [
                            {"X": 0.8141839504241943, "Y": 0.38683247566223145},
                            {"X": 0.8427862524986267, "Y": 0.3868173062801361},
                            {"X": 0.8427990674972534, "Y": 0.40138235688209534},
                            {"X": 0.8141965866088867, "Y": 0.4013974964618683},
                        ],
                    },
                    "Id": "9bdcb99b-63be-4c07-8200-780eaa7a1052",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92437744140625,
                    "Text": "ATKINSON",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1367911696434021,
                            "Height": 0.01499776542186737,
                            "Left": 0.09905943274497986,
                            "Top": 0.42948994040489197,
                        },
                        "Polygon": [
                            {
                                "X": 0.09905943274497986,
                                "Y": 0.42956170439720154,
                            },
                            {
                                "X": 0.23584063351154327,
                                "Y": 0.42948994040489197,
                            },
                            {
                                "X": 0.23585060238838196,
                                "Y": 0.44441625475883484,
                            },
                            {
                                "X": 0.09906869381666183,
                                "Y": 0.44448772072792053,
                            },
                        ],
                    },
                    "Id": "86ab1721-778c-48f6-b8bf-bceb608ed834",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.86483001708984,
                    "Text": "Labour",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07344856858253479,
                            "Height": 0.012892121449112892,
                            "Left": 0.29049208760261536,
                            "Top": 0.4414694905281067,
                        },
                        "Polygon": [
                            {
                                "X": 0.29049208760261536,
                                "Y": 0.44150787591934204,
                            },
                            {"X": 0.36393147706985474, "Y": 0.4414694905281067},
                            {
                                "X": 0.36394065618515015,
                                "Y": 0.45432335138320923,
                            },
                            {"X": 0.2905009090900421, "Y": 0.45436161756515503},
                        ],
                    },
                    "Id": "866e95ae-7b61-45ae-9afe-b699b7116799",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99230194091797,
                    "Text": "Party",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05379088222980499,
                            "Height": 0.01636471226811409,
                            "Left": 0.3710480034351349,
                            "Top": 0.4412554204463959,
                        },
                        "Polygon": [
                            {"X": 0.3710480034351349, "Y": 0.44128352403640747},
                            {"X": 0.4248269200325012, "Y": 0.4412554204463959},
                            {"X": 0.4248389005661011, "Y": 0.4575921595096588},
                            {
                                "X": 0.37105968594551086,
                                "Y": 0.45762014389038086,
                            },
                        ],
                    },
                    "Id": "0d20e06b-f27e-462c-b680-ad3787221ec0",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9043197631836,
                    "Text": "(address",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05754384770989418,
                            "Height": 0.01056667324155569,
                            "Left": 0.5141233801841736,
                            "Top": 0.4372113049030304,
                        },
                        "Polygon": [
                            {"X": 0.5141233801841736, "Y": 0.43724143505096436},
                            {"X": 0.5716589689254761, "Y": 0.4372113049030304},
                            {"X": 0.5716671943664551, "Y": 0.44774797558784485},
                            {"X": 0.5141314268112183, "Y": 0.44777798652648926},
                        ],
                    },
                    "Id": "f8b20245-5eda-4e3a-8b06-ff430aee2f74",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96162414550781,
                    "Text": "in",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.01160053163766861,
                            "Height": 0.008662926964461803,
                            "Left": 0.5761726498603821,
                            "Top": 0.43743741512298584,
                        },
                        "Polygon": [
                            {"X": 0.5761726498603821, "Y": 0.43744346499443054},
                            {"X": 0.5877663493156433, "Y": 0.43743741512298584},
                            {"X": 0.5877732038497925, "Y": 0.446094274520874},
                            {"X": 0.5761794447898865, "Y": 0.4461003243923187},
                        ],
                    },
                    "Id": "d9b1ccb3-0d5e-40ac-9fcd-1b66e77ad61c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.84968566894531,
                    "Text": "London",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04978787899017334,
                            "Height": 0.008752814494073391,
                            "Left": 0.5925198793411255,
                            "Top": 0.43740320205688477,
                        },
                        "Polygon": [
                            {"X": 0.5925198793411255, "Y": 0.4374292492866516},
                            {"X": 0.6423007249832153, "Y": 0.43740320205688477},
                            {"X": 0.6423077583312988, "Y": 0.44613003730773926},
                            {"X": 0.5925267934799194, "Y": 0.44615602493286133},
                        ],
                    },
                    "Id": "c8e485de-fc22-4f0d-9158-57adadd59f85",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94509887695312,
                    "Text": "Garvey",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04866309091448784,
                            "Height": 0.01090792752802372,
                            "Left": 0.7161666750907898,
                            "Top": 0.4372379183769226,
                        },
                        "Polygon": [
                            {"X": 0.7161666750907898, "Y": 0.4372633993625641},
                            {"X": 0.7648205161094666, "Y": 0.4372379183769226},
                            {"X": 0.7648297548294067, "Y": 0.44812047481536865},
                            {"X": 0.7161757946014404, "Y": 0.44814586639404297},
                        ],
                    },
                    "Id": "3a36e0a8-141f-47f3-8314-689e855edb51",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.93270111083984,
                    "Text": "Redmond",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06476590037345886,
                            "Height": 0.008830603212118149,
                            "Left": 0.7695648670196533,
                            "Top": 0.4372868239879608,
                        },
                        "Polygon": [
                            {"X": 0.7695648670196533, "Y": 0.4373207092285156},
                            {"X": 0.8343230485916138, "Y": 0.4372868239879608},
                            {"X": 0.8343307971954346, "Y": 0.4460836350917816},
                            {"X": 0.769572377204895, "Y": 0.44611743092536926},
                        ],
                    },
                    "Id": "f0008340-40c6-4e43-add1-7ee225330958",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.91021728515625,
                    "Text": "*",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.005807613953948021,
                            "Height": 0.004070561844855547,
                            "Left": 0.8388094902038574,
                            "Top": 0.4373885989189148,
                        },
                        "Polygon": [
                            {"X": 0.8388094902038574, "Y": 0.43739163875579834},
                            {"X": 0.8446134924888611, "Y": 0.4373885989189148},
                            {"X": 0.8446170687675476, "Y": 0.4414561092853546},
                            {"X": 0.838813066482544, "Y": 0.44145914912223816},
                        ],
                    },
                    "Id": "aceae24d-43a5-45d3-8de9-fe14998cefb3",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98502349853516,
                    "Text": "Dawn",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06620199978351593,
                            "Height": 0.01482323743402958,
                            "Left": 0.10078901052474976,
                            "Top": 0.45143911242485046,
                        },
                        "Polygon": [
                            {"X": 0.10078901052474976, "Y": 0.4514736235141754},
                            {
                                "X": 0.16698148846626282,
                                "Y": 0.45143911242485046,
                            },
                            {
                                "X": 0.16699101030826569,
                                "Y": 0.46622800827026367,
                            },
                            {"X": 0.10079820454120636, "Y": 0.4662623703479767},
                        ],
                    },
                    "Id": "7e2843e4-4ad1-4bdd-a713-45d5f15ab9fe",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96041870117188,
                    "Text": "Borough",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0566670261323452,
                            "Height": 0.01078647281974554,
                            "Left": 0.5134903788566589,
                            "Top": 0.4497171640396118,
                        },
                        "Polygon": [
                            {"X": 0.5134903788566589, "Y": 0.4497467279434204},
                            {"X": 0.5701489448547363, "Y": 0.4497171640396118},
                            {"X": 0.5701574087142944, "Y": 0.4604741930961609},
                            {"X": 0.5134986042976379, "Y": 0.46050363779067993},
                        ],
                    },
                    "Id": "170b7f6c-14b7-4098-b8fd-3bfb77e4e3c5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97090148925781,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.013194636441767216,
                            "Height": 0.008652405813336372,
                            "Left": 0.5746082663536072,
                            "Top": 0.449656218290329,
                        },
                        "Polygon": [
                            {"X": 0.5746082663536072, "Y": 0.44966307282447815},
                            {"X": 0.5877960920333862, "Y": 0.449656218290329},
                            {"X": 0.5878028869628906, "Y": 0.45830175280570984},
                            {"X": 0.5746150612831116, "Y": 0.458308607339859},
                        ],
                    },
                    "Id": "d38cac70-f4bf-483a-931d-b47c96b5a1af",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 95.82637786865234,
                    "Text": "Lewisham)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07218033075332642,
                            "Height": 0.010882734321057796,
                            "Left": 0.5918126106262207,
                            "Top": 0.44957640767097473,
                        },
                        "Polygon": [
                            {"X": 0.5918126106262207, "Y": 0.4496140480041504},
                            {"X": 0.6639841198921204, "Y": 0.44957640767097473},
                            {"X": 0.6639929413795471, "Y": 0.460421621799469},
                            {"X": 0.5918211936950684, "Y": 0.4604591429233551},
                        ],
                    },
                    "Id": "d7b1ef34-dec6-443d-b00d-bd217f46f580",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94598388671875,
                    "Text": "Kelly",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03283068537712097,
                            "Height": 0.01080690324306488,
                            "Left": 0.7161106467247009,
                            "Top": 0.44963452219963074,
                        },
                        "Polygon": [
                            {"X": 0.7161106467247009, "Y": 0.4496516287326813},
                            {"X": 0.7489322423934937, "Y": 0.44963452219963074},
                            {"X": 0.7489413619041443, "Y": 0.46042436361312866},
                            {"X": 0.716119647026062, "Y": 0.4604414105415344},
                        ],
                    },
                    "Id": "992b1de9-381b-4bc4-ad75-7a45263be98f",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.76778411865234,
                    "Text": "Nicholas",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.057336147874593735,
                            "Height": 0.008854560554027557,
                            "Left": 0.7534793019294739,
                            "Top": 0.4496614336967468,
                        },
                        "Polygon": [
                            {"X": 0.7534793019294739, "Y": 0.4496913254261017},
                            {"X": 0.8108078241348267, "Y": 0.4496614336967468},
                            {"X": 0.8108154535293579, "Y": 0.4584861695766449},
                            {"X": 0.7534868121147156, "Y": 0.4585159718990326},
                        ],
                    },
                    "Id": "87f23f18-72e4-4082-b37c-f6eeb720e269",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.44371032714844,
                    "Text": "J",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0077264877036213875,
                            "Height": 0.008599566295742989,
                            "Left": 0.8146054744720459,
                            "Top": 0.44972389936447144,
                        },
                        "Polygon": [
                            {"X": 0.8146054744720459, "Y": 0.44972795248031616},
                            {"X": 0.8223244547843933, "Y": 0.44972389936447144},
                            {"X": 0.822331964969635, "Y": 0.45831945538520813},
                            {"X": 0.8146129250526428, "Y": 0.45832347869873047},
                        ],
                    },
                    "Id": "304276a9-b4f5-459c-a124-dd47d9bca6ba",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 95.9616928100586,
                    "Text": "**",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.010838829912245274,
                            "Height": 0.0040587857365608215,
                            "Left": 0.8272466659545898,
                            "Top": 0.4496111571788788,
                        },
                        "Polygon": [
                            {"X": 0.8272466659545898, "Y": 0.44961681962013245},
                            {"X": 0.838081955909729, "Y": 0.4496111571788788},
                            {"X": 0.8380855321884155, "Y": 0.45366430282592773},
                            {"X": 0.8272502422332764, "Y": 0.453669935464859},
                        ],
                    },
                    "Id": "a8e6fc18-9109-4ad2-a1aa-6a1e7de652ea",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96228790283203,
                    "Text": "CROSSLEY",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14634709060192108,
                            "Height": 0.015371249057352543,
                            "Left": 0.0993841141462326,
                            "Top": 0.4926571846008301,
                        },
                        "Polygon": [
                            {"X": 0.0993841141462326, "Y": 0.49273258447647095},
                            {"X": 0.24572092294692993, "Y": 0.4926571846008301},
                            {"X": 0.2457312047481537, "Y": 0.507953405380249},
                            {"X": 0.09939361363649368, "Y": 0.5080284476280212},
                        ],
                    },
                    "Id": "cb0e1407-68fb-4e62-b2bf-55e30ee99551",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9633560180664,
                    "Text": "(address",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.058079659938812256,
                            "Height": 0.010714537464082241,
                            "Left": 0.513847827911377,
                            "Top": 0.5006945729255676,
                        },
                        "Polygon": [
                            {"X": 0.513847827911377, "Y": 0.5007244348526001},
                            {"X": 0.5719191431999207, "Y": 0.5006945729255676},
                            {"X": 0.5719274878501892, "Y": 0.5113793611526489},
                            {"X": 0.5138559937477112, "Y": 0.5114091038703918},
                        ],
                    },
                    "Id": "d632bbcb-6cc5-4d16-b415-536aec2c710b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96047973632812,
                    "Text": "in",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.011560672894120216,
                            "Height": 0.008460731245577335,
                            "Left": 0.5763120055198669,
                            "Top": 0.5007668137550354,
                        },
                        "Polygon": [
                            {"X": 0.5763120055198669, "Y": 0.5007727146148682},
                            {"X": 0.5878660082817078, "Y": 0.5007668137550354},
                            {"X": 0.5878726840019226, "Y": 0.509221613407135},
                            {"X": 0.5763186812400818, "Y": 0.5092275142669678},
                        ],
                    },
                    "Id": "749e5eff-88b1-4787-ba36-1f9313cc6a47",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.86953735351562,
                    "Text": "London",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04946150630712509,
                            "Height": 0.008615154772996902,
                            "Left": 0.5928711891174316,
                            "Top": 0.5006815195083618,
                        },
                        "Polygon": [
                            {"X": 0.5928711891174316, "Y": 0.5007069110870361},
                            {"X": 0.642325758934021, "Y": 0.5006815195083618},
                            {"X": 0.6423327326774597, "Y": 0.5092713236808777},
                            {"X": 0.592877984046936, "Y": 0.5092966556549072},
                        ],
                    },
                    "Id": "7d275e50-6760-4807-8334-06e0bf2550c1",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92559051513672,
                    "Text": "Wilmer",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.047759346663951874,
                            "Height": 0.008663591928780079,
                            "Left": 0.7153988480567932,
                            "Top": 0.5006390810012817,
                        },
                        "Polygon": [
                            {"X": 0.7153988480567932, "Y": 0.5006636381149292},
                            {"X": 0.7631508708000183, "Y": 0.5006390810012817},
                            {"X": 0.7631582021713257, "Y": 0.5092781782150269},
                            {"X": 0.715406060218811, "Y": 0.5093026757240295},
                        ],
                    },
                    "Id": "0c839e20-32c2-44b5-8231-0398d070ef94",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.76007080078125,
                    "Text": "Tania",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03885224461555481,
                            "Height": 0.009114890359342098,
                            "Left": 0.7664493918418884,
                            "Top": 0.5003582835197449,
                        },
                        "Polygon": [
                            {"X": 0.7664493918418884, "Y": 0.5003782510757446},
                            {"X": 0.8052937984466553, "Y": 0.5003582835197449},
                            {"X": 0.8053016662597656, "Y": 0.5094532370567322},
                            {"X": 0.7664571404457092, "Y": 0.5094731450080872},
                        ],
                    },
                    "Id": "030474e7-f8ae-4ab6-9e04-729cdf28b6b1",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.8913803100586,
                    "Text": "L",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.008101928979158401,
                            "Height": 0.008321222849190235,
                            "Left": 0.8091042637825012,
                            "Top": 0.500748872756958,
                        },
                        "Polygon": [
                            {"X": 0.8091042637825012, "Y": 0.5007530450820923},
                            {"X": 0.8171989321708679, "Y": 0.500748872756958},
                            {"X": 0.8172062039375305, "Y": 0.5090659260749817},
                            {"X": 0.809111475944519, "Y": 0.509070098400116},
                        ],
                    },
                    "Id": "d775da41-7115-4ac1-aa79-36da86297306",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 95.70893859863281,
                    "Text": "*",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.005205954425036907,
                            "Height": 0.003907948732376099,
                            "Left": 0.8219414949417114,
                            "Top": 0.500805675983429,
                        },
                        "Polygon": [
                            {"X": 0.8219414949417114, "Y": 0.5008083581924438},
                            {"X": 0.8271440267562866, "Y": 0.500805675983429},
                            {"X": 0.8271474838256836, "Y": 0.5047109723091125},
                            {"X": 0.8219448924064636, "Y": 0.5047135949134827},
                        ],
                    },
                    "Id": "3242e208-247c-43c3-9da4-80cff653b820",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99391174316406,
                    "Text": "The",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.040568020194768906,
                            "Height": 0.013031207956373692,
                            "Left": 0.28973525762557983,
                            "Top": 0.5046571493148804,
                        },
                        "Polygon": [
                            {"X": 0.28973525762557983, "Y": 0.5046780109405518},
                            {"X": 0.3302941620349884, "Y": 0.5046571493148804},
                            {"X": 0.33030328154563904, "Y": 0.5176676511764526},
                            {"X": 0.28974419832229614, "Y": 0.5176883935928345},
                        ],
                    },
                    "Id": "3b68e359-ded1-4b01-bb10-3db97586d52b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98760223388672,
                    "Text": "Green",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06437677890062332,
                            "Height": 0.013392813503742218,
                            "Left": 0.33773496747016907,
                            "Top": 0.5044366717338562,
                        },
                        "Polygon": [
                            {"X": 0.33773496747016907, "Y": 0.5044696927070618},
                            {"X": 0.4021020531654358, "Y": 0.5044366717338562},
                            {"X": 0.4021117389202118, "Y": 0.5177965760231018},
                            {"X": 0.3377443552017212, "Y": 0.5178294777870178},
                        ],
                    },
                    "Id": "50ff677b-3523-4275-adb4-d18eadae5486",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98925018310547,
                    "Text": "Party",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.053478214889764786,
                            "Height": 0.016320466995239258,
                            "Left": 0.4103134572505951,
                            "Top": 0.5044715404510498,
                        },
                        "Polygon": [
                            {"X": 0.4103134572505951, "Y": 0.5044990181922913},
                            {"X": 0.4637795090675354, "Y": 0.5044715404510498},
                            {"X": 0.4637916684150696, "Y": 0.5207647085189819},
                            {"X": 0.4103253185749054, "Y": 0.5207920074462891},
                        ],
                    },
                    "Id": "961407f6-a2ac-4bab-89a6-3d6409fc31bd",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98291015625,
                    "Text": "Tim",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04397975653409958,
                            "Height": 0.014743184670805931,
                            "Left": 0.09925346821546555,
                            "Top": 0.5147435665130615,
                        },
                        "Polygon": [
                            {"X": 0.09925346821546555, "Y": 0.5147660970687866},
                            {"X": 0.1432238668203354, "Y": 0.5147435665130615},
                            {"X": 0.14323322474956512, "Y": 0.5294643640518188},
                            {"X": 0.09926260262727737, "Y": 0.5294867753982544},
                        ],
                    },
                    "Id": "c2824581-0142-497a-ba5a-d956cdd8a12b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.95552825927734,
                    "Text": "Borough",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05678520351648331,
                            "Height": 0.010652567259967327,
                            "Left": 0.5135619044303894,
                            "Top": 0.5131126046180725,
                        },
                        "Polygon": [
                            {"X": 0.5135619044303894, "Y": 0.5131416916847229},
                            {"X": 0.570338785648346, "Y": 0.5131126046180725},
                            {"X": 0.5703471302986145, "Y": 0.5237361788749695},
                            {"X": 0.5135700702667236, "Y": 0.5237652063369751},
                        ],
                    },
                    "Id": "b735afa1-19f8-4b2b-84c4-339a74c2010d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96329498291016,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.01314293872565031,
                            "Height": 0.008893240243196487,
                            "Left": 0.5746943354606628,
                            "Top": 0.5127789974212646,
                        },
                        "Polygon": [
                            {"X": 0.5746943354606628, "Y": 0.5127857327461243},
                            {"X": 0.5878302454948425, "Y": 0.5127789974212646},
                            {"X": 0.587837278842926, "Y": 0.5216655135154724},
                            {"X": 0.5747013092041016, "Y": 0.521672248840332},
                        ],
                    },
                    "Id": "b2ed293f-07f6-445d-870f-6e4d83f7c5d2",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.27190399169922,
                    "Text": "Lewisham)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07233836501836777,
                            "Height": 0.010717183351516724,
                            "Left": 0.5915666222572327,
                            "Top": 0.5129258036613464,
                        },
                        "Polygon": [
                            {"X": 0.5915666222572327, "Y": 0.5129628777503967},
                            {"X": 0.6638962626457214, "Y": 0.5129258036613464},
                            {"X": 0.6639049649238586, "Y": 0.5236060619354248},
                            {"X": 0.591575026512146, "Y": 0.5236430168151855},
                        ],
                    },
                    "Id": "46054c85-288e-40a3-9997-410df187ca99",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.33879852294922,
                    "Text": "Wiaterska",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0676223561167717,
                            "Height": 0.008769052103161812,
                            "Left": 0.7155911326408386,
                            "Top": 0.5127924084663391,
                        },
                        "Polygon": [
                            {"X": 0.7155911326408386, "Y": 0.5128270387649536},
                            {"X": 0.7832059860229492, "Y": 0.5127924084663391},
                            {"X": 0.7832134962081909, "Y": 0.5215269327163696},
                            {"X": 0.7155984044075012, "Y": 0.5215614438056946},
                        ],
                    },
                    "Id": "e6f7dc41-cae6-4fef-a378-df2fc2e5bd13",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.76358032226562,
                    "Text": "Roksana",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.059126369655132294,
                            "Height": 0.008619316853582859,
                            "Left": 0.7879095077514648,
                            "Top": 0.5129773020744324,
                        },
                        "Polygon": [
                            {"X": 0.7879095077514648, "Y": 0.5130075812339783},
                            {"X": 0.8470283150672913, "Y": 0.5129773020744324},
                            {"X": 0.8470358848571777, "Y": 0.5215664505958557},
                            {"X": 0.787916898727417, "Y": 0.5215966105461121},
                        ],
                    },
                    "Id": "e79719d1-dd3d-4290-bebc-7d4b18eb9d21",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.83457946777344,
                    "Text": "M",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.012143059633672237,
                            "Height": 0.008496369235217571,
                            "Left": 0.8514286279678345,
                            "Top": 0.5129026770591736,
                        },
                        "Polygon": [
                            {"X": 0.8514286279678345, "Y": 0.5129088759422302},
                            {"X": 0.8635641932487488, "Y": 0.5129026770591736},
                            {"X": 0.8635717034339905, "Y": 0.521392822265625},
                            {"X": 0.8514361381530762, "Y": 0.5213990211486816},
                        ],
                    },
                    "Id": "d36802eb-f6d3-427b-b26f-da60171407df",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.21509552001953,
                    "Text": "**",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.011245054192841053,
                            "Height": 0.003931088373064995,
                            "Left": 0.8679940104484558,
                            "Top": 0.5129423141479492,
                        },
                        "Polygon": [
                            {"X": 0.8679940104484558, "Y": 0.5129480957984924},
                            {"X": 0.879235565662384, "Y": 0.5129423141479492},
                            {"X": 0.8792390823364258, "Y": 0.5168676972389221},
                            {"X": 0.8679974675178528, "Y": 0.5168734192848206},
                        ],
                    },
                    "Id": "53483193-3145-459e-9b17-02b144afd79b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9620132446289,
                    "Text": "HARDING",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.12150311470031738,
                            "Height": 0.014916855841875076,
                            "Left": 0.10060852020978928,
                            "Top": 0.5560656189918518,
                        },
                        "Polygon": [
                            {"X": 0.10060852020978928, "Y": 0.5561270713806152},
                            {"X": 0.22210177779197693, "Y": 0.5560656189918518},
                            {"X": 0.22211162745952606, "Y": 0.5709213018417358},
                            {"X": 0.10061775147914886, "Y": 0.5709824562072754},
                        ],
                    },
                    "Id": "d463cb9a-ea5a-41f1-b2de-cbf0ef461f3c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.93134307861328,
                    "Text": "Liberal",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06957215070724487,
                            "Height": 0.013315620832145214,
                            "Left": 0.2908428907394409,
                            "Top": 0.5676462054252625,
                        },
                        "Polygon": [
                            {"X": 0.2908428907394409, "Y": 0.5676813125610352},
                            {"X": 0.3604055941104889, "Y": 0.5676462054252625},
                            {"X": 0.3604150414466858, "Y": 0.5809268951416016},
                            {"X": 0.29085201025009155, "Y": 0.5809618234634399},
                        ],
                    },
                    "Id": "745a8e38-268b-4fe8-9c70-bc64d4ebb7c5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.80079650878906,
                    "Text": "Democrats",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.11198054254055023,
                            "Height": 0.013159946538507938,
                            "Left": 0.36842653155326843,
                            "Top": 0.5679779648780823,
                        },
                        "Polygon": [
                            {"X": 0.36842653155326843, "Y": 0.5680344104766846},
                            {"X": 0.48039719462394714, "Y": 0.5679779648780823},
                            {"X": 0.48040705919265747, "Y": 0.5810816884040833},
                            {"X": 0.36843588948249817, "Y": 0.5811379551887512},
                        ],
                    },
                    "Id": "79a3807e-f816-47ac-9dd0-31a1c83b05ad",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.93341827392578,
                    "Text": "(address",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.058075811713933945,
                            "Height": 0.010658947750926018,
                            "Left": 0.5137732625007629,
                            "Top": 0.5639289021492004,
                        },
                        "Polygon": [
                            {"X": 0.5137732625007629, "Y": 0.5639581680297852},
                            {"X": 0.571840763092041, "Y": 0.5639289021492004},
                            {"X": 0.5718490481376648, "Y": 0.5745586156845093},
                            {"X": 0.5137813687324524, "Y": 0.5745878219604492},
                        ],
                    },
                    "Id": "c316d4a2-6226-47e1-ae46-ec42de583791",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96644592285156,
                    "Text": "in",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.011382153257727623,
                            "Height": 0.00862267054617405,
                            "Left": 0.5762742161750793,
                            "Top": 0.5639817714691162,
                        },
                        "Polygon": [
                            {"X": 0.5762742161750793, "Y": 0.5639874935150146},
                            {"X": 0.5876495838165283, "Y": 0.5639817714691162},
                            {"X": 0.5876563787460327, "Y": 0.5725986957550049},
                            {"X": 0.5762810111045837, "Y": 0.5726044178009033},
                        ],
                    },
                    "Id": "35eeff4a-17d5-41e4-b14d-f419d9bf5dbf",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.85153198242188,
                    "Text": "London",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.049798958003520966,
                            "Height": 0.008776597678661346,
                            "Left": 0.5925126671791077,
                            "Top": 0.5638841986656189,
                        },
                        "Polygon": [
                            {"X": 0.5925126671791077, "Y": 0.5639093518257141},
                            {"X": 0.642304539680481, "Y": 0.5638841986656189},
                            {"X": 0.6423116326332092, "Y": 0.5726357698440552},
                            {"X": 0.5925195813179016, "Y": 0.5726608037948608},
                        ],
                    },
                    "Id": "41c378f3-eb96-4175-be3e-f7033c5cb479",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9259262084961,
                    "Text": "Niekirk",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.046418532729148865,
                            "Height": 0.008782383054494858,
                            "Left": 0.71607905626297,
                            "Top": 0.5638388395309448,
                        },
                        "Polygon": [
                            {"X": 0.71607905626297, "Y": 0.5638622641563416},
                            {"X": 0.7624901533126831, "Y": 0.5638388395309448},
                            {"X": 0.76249760389328, "Y": 0.572597861289978},
                            {"X": 0.7160863876342773, "Y": 0.57262122631073},
                        ],
                    },
                    "Id": "206483d1-b545-4b04-9789-30512a39e28b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.93864440917969,
                    "Text": "Charles",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05150013417005539,
                            "Height": 0.008829813450574875,
                            "Left": 0.7665860056877136,
                            "Top": 0.563813328742981,
                        },
                        "Polygon": [
                            {"X": 0.7665860056877136, "Y": 0.563839316368103},
                            {"X": 0.8180784583091736, "Y": 0.563813328742981},
                            {"X": 0.8180860877037048, "Y": 0.57261723279953},
                            {"X": 0.7665934562683105, "Y": 0.5726431608200073},
                        ],
                    },
                    "Id": "29333967-a0b1-4dbd-ad57-faad6ff8a63e",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.9485855102539,
                    "Text": "J",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.007824549451470375,
                            "Height": 0.008717146702110767,
                            "Left": 0.8219206929206848,
                            "Top": 0.5639663338661194,
                        },
                        "Polygon": [
                            {"X": 0.8219206929206848, "Y": 0.5639703273773193},
                            {"X": 0.8297376036643982, "Y": 0.5639663338661194},
                            {"X": 0.8297452330589294, "Y": 0.5726795792579651},
                            {"X": 0.8219282627105713, "Y": 0.5726835131645203},
                        ],
                    },
                    "Id": "3ce996ec-a2ec-4497-b707-46507c2c837b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.18490600585938,
                    "Text": "W",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.014617103151977062,
                            "Height": 0.00867766048759222,
                            "Left": 0.8339850306510925,
                            "Top": 0.5638127326965332,
                        },
                        "Polygon": [
                            {"X": 0.8339850306510925, "Y": 0.5638200640678406},
                            {"X": 0.8485944867134094, "Y": 0.5638127326965332},
                            {"X": 0.8486021161079407, "Y": 0.5724830031394958},
                            {"X": 0.833992600440979, "Y": 0.572490394115448},
                        ],
                    },
                    "Id": "baf67f0a-1ec9-4254-a56c-5575d17c4ff2",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.53350830078125,
                    "Text": "*",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.005463228095322847,
                            "Height": 0.003939294256269932,
                            "Left": 0.8528037071228027,
                            "Top": 0.5640483498573303,
                        },
                        "Polygon": [
                            {"X": 0.8528037071228027, "Y": 0.56405109167099},
                            {"X": 0.8582634329795837, "Y": 0.5640483498573303},
                            {"X": 0.8582669496536255, "Y": 0.5679848790168762},
                            {"X": 0.8528071641921997, "Y": 0.5679876208305359},
                        ],
                    },
                    "Id": "bb272a17-30ff-4f6a-a99f-94adf75f815b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98571014404297,
                    "Text": "Alan",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.053108908236026764,
                            "Height": 0.014738841913640499,
                            "Left": 0.09938479214906693,
                            "Top": 0.578180730342865,
                        },
                        "Polygon": [
                            {"X": 0.09938479214906693, "Y": 0.5782073736190796},
                            {"X": 0.15248429775238037, "Y": 0.578180730342865},
                            {"X": 0.1524937003850937, "Y": 0.5928930044174194},
                            {"X": 0.09939392656087875, "Y": 0.5929195284843445},
                        ],
                    },
                    "Id": "2b224e61-820e-44da-8dbd-ba119229bf48",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.77397918701172,
                    "Text": "Francis",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08627965301275253,
                            "Height": 0.015012906864285469,
                            "Left": 0.16195248067378998,
                            "Top": 0.5780068039894104,
                        },
                        "Polygon": [
                            {"X": 0.16195248067378998, "Y": 0.5780501365661621},
                            {"X": 0.24822208285331726, "Y": 0.5780068039894104},
                            {"X": 0.2482321411371231, "Y": 0.5929765701293945},
                            {"X": 0.1619621068239212, "Y": 0.5930197238922119},
                        ],
                    },
                    "Id": "58261409-1e35-4807-b8f8-75bec68f64f2",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96543884277344,
                    "Text": "Borough",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05653240159153938,
                            "Height": 0.010772802866995335,
                            "Left": 0.5136257410049438,
                            "Top": 0.5763059258460999,
                        },
                        "Polygon": [
                            {"X": 0.5136257410049438, "Y": 0.5763343572616577},
                            {"X": 0.5701497197151184, "Y": 0.5763059258460999},
                            {"X": 0.5701581239700317, "Y": 0.5870504379272461},
                            {"X": 0.5136339664459229, "Y": 0.5870787501335144},
                        ],
                    },
                    "Id": "dde41795-9dc7-45a8-9ff0-c28139bc12e6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96923065185547,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.013177461922168732,
                            "Height": 0.008660237304866314,
                            "Left": 0.5745961666107178,
                            "Top": 0.5761638879776001,
                        },
                        "Polygon": [
                            {"X": 0.5745961666107178, "Y": 0.5761705040931702},
                            {"X": 0.5877667665481567, "Y": 0.5761638879776001},
                            {"X": 0.5877736210823059, "Y": 0.5848175287246704},
                            {"X": 0.5746029615402222, "Y": 0.5848240852355957},
                        ],
                    },
                    "Id": "40110550-406b-4468-a5fb-be22c3753d94",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.15233612060547,
                    "Text": "Lewisham)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07226182520389557,
                            "Height": 0.010778921656310558,
                            "Left": 0.5918365716934204,
                            "Top": 0.5761432647705078,
                        },
                        "Polygon": [
                            {"X": 0.5918365716934204, "Y": 0.576179563999176},
                            {"X": 0.6640896201133728, "Y": 0.5761432647705078},
                            {"X": 0.6640983819961548, "Y": 0.5868859887123108},
                            {"X": 0.5918450951576233, "Y": 0.5869221687316895},
                        ],
                    },
                    "Id": "79e81c38-db20-4a12-aa5e-4984be5788c6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.88738250732422,
                    "Text": "Clarke",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0435868501663208,
                            "Height": 0.008875560946762562,
                            "Left": 0.7159947752952576,
                            "Top": 0.5760898590087891,
                        },
                        "Polygon": [
                            {"X": 0.7159947752952576, "Y": 0.5761117935180664},
                            {"X": 0.7595741152763367, "Y": 0.5760898590087891},
                            {"X": 0.7595816254615784, "Y": 0.5849435925483704},
                            {"X": 0.7160021662712097, "Y": 0.5849654078483582},
                        ],
                    },
                    "Id": "fd5fed05-f5cd-4316-977b-0f454bdb52b8",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.82173156738281,
                    "Text": "Shannon",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.058658499270677567,
                            "Height": 0.008574153296649456,
                            "Left": 0.7646329998970032,
                            "Top": 0.576206386089325,
                        },
                        "Polygon": [
                            {"X": 0.7646329998970032, "Y": 0.5762358903884888},
                            {"X": 0.8232840895652771, "Y": 0.576206386089325},
                            {"X": 0.823291540145874, "Y": 0.5847511291503906},
                            {"X": 0.7646402716636658, "Y": 0.5847805142402649},
                        ],
                    },
                    "Id": "c880eb9a-de22-4d00-9fa1-08fce68f2b85",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 63.252532958984375,
                    "Text": "I",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0036478715483099222,
                            "Height": 0.008305382914841175,
                            "Left": 0.8286896347999573,
                            "Top": 0.5763481259346008,
                        },
                        "Polygon": [
                            {"X": 0.8286896347999573, "Y": 0.5763499736785889},
                            {"X": 0.8323302268981934, "Y": 0.5763481259346008},
                            {"X": 0.832337498664856, "Y": 0.5846517086029053},
                            {"X": 0.8286968469619751, "Y": 0.5846534967422485},
                        ],
                    },
                    "Id": "b7589599-dd47-4ca3-8e68-280cb218a3b6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.81639862060547,
                    "Text": "**",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.010721702128648758,
                            "Height": 0.0039660632610321045,
                            "Left": 0.8370484113693237,
                            "Top": 0.5762375593185425,
                        },
                        "Polygon": [
                            {"X": 0.8370484113693237, "Y": 0.576242983341217},
                            {"X": 0.847766637802124, "Y": 0.5762375593185425},
                            {"X": 0.8477701544761658, "Y": 0.5801982283592224},
                            {"X": 0.8370519280433655, "Y": 0.580203652381897},
                        ],
                    },
                    "Id": "742862c5-199f-4512-a710-8cbcabc6a1c8",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.93289947509766,
                    "Text": "QADAR",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.09405231475830078,
                            "Height": 0.014996449463069439,
                            "Left": 0.09999311715364456,
                            "Top": 0.6193125247955322,
                        },
                        "Polygon": [
                            {"X": 0.09999311715364456, "Y": 0.6193591952323914},
                            {"X": 0.19403566420078278, "Y": 0.6193125247955322},
                            {"X": 0.19404542446136475, "Y": 0.6342625021934509},
                            {"X": 0.10000240057706833, "Y": 0.6343089938163757},
                        ],
                    },
                    "Id": "79210e66-b574-4a00-a329-65402a7a9ea8",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.79671478271484,
                    "Text": "Conservatives",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.14849162101745605,
                            "Height": 0.013586771674454212,
                            "Left": 0.29034939408302307,
                            "Top": 0.6308904886245728,
                        },
                        "Polygon": [
                            {"X": 0.29034939408302307, "Y": 0.630963921546936},
                            {"X": 0.43883103132247925, "Y": 0.6308904886245728},
                            {"X": 0.43884098529815674, "Y": 0.6444041132926941},
                            {"X": 0.29035866260528564, "Y": 0.6444772481918335},
                        ],
                    },
                    "Id": "b1be16c0-c2c0-48ba-8192-ab8a055e40e0",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94385528564453,
                    "Text": "(address",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05823894590139389,
                            "Height": 0.010476973839104176,
                            "Left": 0.5137097239494324,
                            "Top": 0.6269196271896362,
                        },
                        "Polygon": [
                            {"X": 0.5137097239494324, "Y": 0.6269484162330627},
                            {"X": 0.5719404816627502, "Y": 0.6269196271896362},
                            {"X": 0.5719486474990845, "Y": 0.637367844581604},
                            {"X": 0.5137177109718323, "Y": 0.6373965740203857},
                        ],
                    },
                    "Id": "c2f4faa8-7907-4a5b-abc6-f7219428b9ab",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97176361083984,
                    "Text": "in",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.011345136910676956,
                            "Height": 0.00859938096255064,
                            "Left": 0.5762984156608582,
                            "Top": 0.6269596219062805,
                        },
                        "Polygon": [
                            {"X": 0.5762984156608582, "Y": 0.6269652843475342},
                            {"X": 0.5876367688179016, "Y": 0.6269596219062805},
                            {"X": 0.587643563747406, "Y": 0.6355534195899963},
                            {"X": 0.5763052105903625, "Y": 0.6355590224266052},
                        ],
                    },
                    "Id": "0197fe23-9303-4359-880a-31951e038327",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.88485717773438,
                    "Text": "London",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.049671720713377,
                            "Height": 0.008728960528969765,
                            "Left": 0.5926021337509155,
                            "Top": 0.6269599795341492,
                        },
                        "Polygon": [
                            {"X": 0.5926021337509155, "Y": 0.6269845962524414},
                            {"X": 0.6422668099403381, "Y": 0.6269599795341492},
                            {"X": 0.6422738432884216, "Y": 0.6356644034385681},
                            {"X": 0.5926090478897095, "Y": 0.6356889605522156},
                        ],
                    },
                    "Id": "76b4371b-038f-4b4a-8159-65c709586388",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.7143325805664,
                    "Text": "Qazi",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.030901199206709862,
                            "Height": 0.00868377834558487,
                            "Left": 0.7161157727241516,
                            "Top": 0.6268940567970276,
                        },
                        "Polygon": [
                            {"X": 0.7161157727241516, "Y": 0.6269093751907349},
                            {"X": 0.7470096945762634, "Y": 0.6268940567970276},
                            {"X": 0.7470170259475708, "Y": 0.6355625987052917},
                            {"X": 0.7161230444908142, "Y": 0.6355778574943542},
                        ],
                    },
                    "Id": "7083f705-4e01-4545-8d72-974ad153be03",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.76701354980469,
                    "Text": "Abdul",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0388210192322731,
                            "Height": 0.008770182728767395,
                            "Left": 0.7509669065475464,
                            "Top": 0.6268494129180908,
                        },
                        "Polygon": [
                            {"X": 0.7509669065475464, "Y": 0.6268686652183533},
                            {"X": 0.7897803783416748, "Y": 0.6268494129180908},
                            {"X": 0.7897878885269165, "Y": 0.6356004476547241},
                            {"X": 0.7509742975234985, "Y": 0.6356196403503418},
                        ],
                    },
                    "Id": "0f7020d8-e291-4ad6-9dc4-6d22406b3cc6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.79510498046875,
                    "Text": "Q",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.012076867744326591,
                            "Height": 0.008709504269063473,
                            "Left": 0.7941505908966064,
                            "Top": 0.6270571947097778,
                        },
                        "Polygon": [
                            {"X": 0.7941505908966064, "Y": 0.6270631551742554},
                            {"X": 0.8062199354171753, "Y": 0.6270571947097778},
                            {"X": 0.806227445602417, "Y": 0.6357607245445251},
                            {"X": 0.7941581010818481, "Y": 0.6357666850090027},
                        ],
                    },
                    "Id": "803981a7-5025-41cc-89b3-d12e67a0ae82",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.66498565673828,
                    "Text": "*",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0053612831979990005,
                            "Height": 0.004342852625995874,
                            "Left": 0.8103842735290527,
                            "Top": 0.626857578754425,
                        },
                        "Polygon": [
                            {"X": 0.8103842735290527, "Y": 0.6268602013587952},
                            {"X": 0.8157418370246887, "Y": 0.626857578754425},
                            {"X": 0.8157455921173096, "Y": 0.6311977505683899},
                            {"X": 0.8103880882263184, "Y": 0.6312004327774048},
                        ],
                    },
                    "Id": "65c94d2c-caa4-4c9b-b8e3-4f2c46ed9f5b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.29061889648438,
                    "Text": "Siama",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07505691051483154,
                            "Height": 0.015140949748456478,
                            "Left": 0.10013869404792786,
                            "Top": 0.6411055326461792,
                        },
                        "Polygon": [
                            {"X": 0.10013869404792786, "Y": 0.6411425471305847},
                            {"X": 0.17518582940101624, "Y": 0.6411055326461792},
                            {"X": 0.1751956045627594, "Y": 0.6562096476554871},
                            {"X": 0.10014807432889938, "Y": 0.6562464833259583},
                        ],
                    },
                    "Id": "393d9dff-f936-47d7-97aa-ffc099bf1a8a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.94949340820312,
                    "Text": "Borough",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05666700378060341,
                            "Height": 0.010795128531754017,
                            "Left": 0.5135375261306763,
                            "Top": 0.6391915082931519,
                        },
                        "Polygon": [
                            {"X": 0.5135375261306763, "Y": 0.6392194628715515},
                            {"X": 0.5701960921287537, "Y": 0.6391915082931519},
                            {"X": 0.5702045559883118, "Y": 0.6499587893486023},
                            {"X": 0.5135457515716553, "Y": 0.6499866247177124},
                        ],
                    },
                    "Id": "d56315c6-74a4-4cb5-a1a2-52f0b72a748f",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97895050048828,
                    "Text": "of",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.013278234750032425,
                            "Height": 0.008943282999098301,
                            "Left": 0.5745636820793152,
                            "Top": 0.6390106081962585,
                        },
                        "Polygon": [
                            {"X": 0.5745636820793152, "Y": 0.6390171647071838},
                            {"X": 0.5878348350524902, "Y": 0.6390106081962585},
                            {"X": 0.5878418684005737, "Y": 0.647947371006012},
                            {"X": 0.5745706558227539, "Y": 0.6479538679122925},
                        ],
                    },
                    "Id": "3d0d7278-1d72-4908-9b75-4fae04f1a6c5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 95.60517883300781,
                    "Text": "Lewisham)",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.07262308150529861,
                            "Height": 0.010805570520460606,
                            "Left": 0.5917080044746399,
                            "Top": 0.6391021609306335,
                        },
                        "Polygon": [
                            {"X": 0.5917080044746399, "Y": 0.6391380429267883},
                            {"X": 0.6643223166465759, "Y": 0.6391021609306335},
                            {"X": 0.6643310785293579, "Y": 0.6498720645904541},
                            {"X": 0.5917165279388428, "Y": 0.6499077677726746},
                        ],
                    },
                    "Id": "801bed18-c8b4-43a6-ad46-e4826cff45d2",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.57429504394531,
                    "Text": "Baksi",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03688858449459076,
                            "Height": 0.008618202060461044,
                            "Left": 0.716232419013977,
                            "Top": 0.6392120718955994,
                        },
                        "Polygon": [
                            {"X": 0.716232419013977, "Y": 0.6392303109169006},
                            {"X": 0.7531136870384216, "Y": 0.6392120718955994},
                            {"X": 0.7531209588050842, "Y": 0.6478121280670166},
                            {"X": 0.7162395715713501, "Y": 0.6478303074836731},
                        ],
                    },
                    "Id": "8311ac0b-cdb9-4cdd-8287-229107084207",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.7775650024414,
                    "Text": "Nikolas",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.048923786729574203,
                            "Height": 0.008726995438337326,
                            "Left": 0.7575073838233948,
                            "Top": 0.6392203569412231,
                        },
                        "Polygon": [
                            {"X": 0.7575073838233948, "Y": 0.6392444968223572},
                            {"X": 0.8064236044883728, "Y": 0.6392203569412231},
                            {"X": 0.8064311742782593, "Y": 0.6479232907295227},
                            {"X": 0.7575147151947021, "Y": 0.647947371006012},
                        ],
                    },
                    "Id": "5364dddf-4a73-4370-be4c-deeea65e56a6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 88.31393432617188,
                    "Text": "**",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.011022998951375484,
                            "Height": 0.003929123282432556,
                            "Left": 0.8110170960426331,
                            "Top": 0.6392341256141663,
                        },
                        "Polygon": [
                            {"X": 0.8110170960426331, "Y": 0.6392395496368408},
                            {"X": 0.8220366835594177, "Y": 0.6392341256141663},
                            {"X": 0.8220401406288147, "Y": 0.6431578397750854},
                            {"X": 0.8110204935073853, "Y": 0.64316326379776},
                        ],
                    },
                    "Id": "bf261c7a-5e43-4138-b994-c8b5019eff48",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99298095703125,
                    "Text": "The",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04098949953913689,
                            "Height": 0.013314565643668175,
                            "Left": 0.05939551070332527,
                            "Top": 0.6859458088874817,
                        },
                        "Polygon": [
                            {"X": 0.05939551070332527, "Y": 0.6859657168388367},
                            {"X": 0.10037675499916077, "Y": 0.6859458088874817},
                            {"X": 0.10038501024246216, "Y": 0.699240505695343},
                            {"X": 0.05940357968211174, "Y": 0.6992603540420532},
                        ],
                    },
                    "Id": "64e5d69c-860e-47df-b5fa-96b81f78891a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9908447265625,
                    "Text": "persons",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08279118686914444,
                            "Height": 0.013931897468864918,
                            "Left": 0.1080918163061142,
                            "Top": 0.6889026761054993,
                        },
                        "Polygon": [
                            {"X": 0.1080918163061142, "Y": 0.6889429092407227},
                            {"X": 0.19087395071983337, "Y": 0.6889026761054993},
                            {"X": 0.19088301062583923, "Y": 0.7027945518493652},
                            {"X": 0.10810048133134842, "Y": 0.7028346061706543},
                        ],
                    },
                    "Id": "2ab75076-b6c6-4c03-bf27-4fa638abb9cf",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99467468261719,
                    "Text": "above",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06325999647378922,
                            "Height": 0.012896640226244926,
                            "Left": 0.19787311553955078,
                            "Top": 0.686517596244812,
                        },
                        "Polygon": [
                            {"X": 0.19787311553955078, "Y": 0.6865484118461609},
                            {"X": 0.2611244022846222, "Y": 0.686517596244812},
                            {"X": 0.2611331045627594, "Y": 0.6993836164474487},
                            {"X": 0.1978815495967865, "Y": 0.6994142532348633},
                        ],
                    },
                    "Id": "8f2556f6-33fe-478e-96e1-1b28a623c762",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99008178710938,
                    "Text": "stand",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05703917518258095,
                            "Height": 0.012719348073005676,
                            "Left": 0.26813873648643494,
                            "Top": 0.6865771412849426,
                        },
                        "Polygon": [
                            {"X": 0.26813873648643494, "Y": 0.6866048574447632},
                            {"X": 0.32516905665397644, "Y": 0.6865771412849426},
                            {"X": 0.3251779079437256, "Y": 0.6992688179016113},
                            {"X": 0.268147349357605, "Y": 0.6992964744567871},
                        ],
                    },
                    "Id": "a7049f7e-c590-41f8-825c-89bf5ea4e194",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9552993774414,
                    "Text": "validly",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06629969924688339,
                            "Height": 0.016622979193925858,
                            "Left": 0.33134621381759644,
                            "Top": 0.6860625147819519,
                        },
                        "Polygon": [
                            {"X": 0.33134621381759644, "Y": 0.6860947608947754},
                            {"X": 0.3976338803768158, "Y": 0.6860625147819519},
                            {"X": 0.39764589071273804, "Y": 0.7026534080505371},
                            {"X": 0.33135783672332764, "Y": 0.7026854753494263},
                        ],
                    },
                    "Id": "f3dd540a-720e-4449-aad6-87810fb0c3ed",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97374725341797,
                    "Text": "nominated",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.10835833102464676,
                            "Height": 0.01284264400601387,
                            "Left": 0.4049279987812042,
                            "Top": 0.6863793134689331,
                        },
                        "Polygon": [
                            {"X": 0.4049279987812042, "Y": 0.6864320635795593},
                            {"X": 0.5132765769958496, "Y": 0.6863793134689331},
                            {"X": 0.5132863521575928, "Y": 0.6991694569587708},
                            {"X": 0.4049372971057892, "Y": 0.6992219686508179},
                        ],
                    },
                    "Id": "24502c61-7933-4e15-847c-95417715a559",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98711395263672,
                    "Text": "in",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.01736023649573326,
                            "Height": 0.012775221839547157,
                            "Left": 0.521034300327301,
                            "Top": 0.6863301396369934,
                        },
                        "Polygon": [
                            {"X": 0.521034300327301, "Y": 0.6863386034965515},
                            {"X": 0.5383846759796143, "Y": 0.6863301396369934},
                            {"X": 0.538394570350647, "Y": 0.6990969777107239},
                            {"X": 0.521044135093689, "Y": 0.6991053819656372},
                        ],
                    },
                    "Id": "3489a51e-54eb-4fac-955b-0d6920060c65",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99810791015625,
                    "Text": "the",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03295949101448059,
                            "Height": 0.012667914852499962,
                            "Left": 0.5451053380966187,
                            "Top": 0.686590313911438,
                        },
                        "Polygon": [
                            {"X": 0.5451053380966187, "Y": 0.6866063475608826},
                            {"X": 0.5780548453330994, "Y": 0.686590313911438},
                            {"X": 0.5780647993087769, "Y": 0.6992422938346863},
                            {"X": 0.5451151132583618, "Y": 0.6992582678794861},
                        ],
                    },
                    "Id": "e6ff8255-d23e-46da-bb36-db59be757d6a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92583465576172,
                    "Text": "Deptford",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08885450661182404,
                            "Height": 0.01631760783493519,
                            "Left": 0.5856120586395264,
                            "Top": 0.6861282587051392,
                        },
                        "Polygon": [
                            {"X": 0.5856120586395264, "Y": 0.6861714720726013},
                            {"X": 0.6744531989097595, "Y": 0.6861282587051392},
                            {"X": 0.6744665503501892, "Y": 0.7024028301239014},
                            {"X": 0.5856249332427979, "Y": 0.7024458646774292},
                        ],
                    },
                    "Id": "92e1adfa-c526-4a77-b975-3e61dd462447",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97024536132812,
                    "Text": "By-election",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.11552593857049942,
                            "Height": 0.016473617404699326,
                            "Left": 0.6821625828742981,
                            "Top": 0.686246395111084,
                        },
                        "Polygon": [
                            {"X": 0.6821625828742981, "Y": 0.6863025426864624},
                            {"X": 0.7976743578910828, "Y": 0.686246395111084},
                            {"X": 0.7976885437965393, "Y": 0.7026640772819519},
                            {"X": 0.6821761131286621, "Y": 0.7027199864387512},
                        ],
                    },
                    "Id": "d259edc0-7902-42dc-96f0-c25e49d7b07b",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99396514892578,
                    "Text": "with",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.041632771492004395,
                            "Height": 0.01305321790277958,
                            "Left": 0.8041268587112427,
                            "Top": 0.6862016320228577,
                        },
                        "Polygon": [
                            {"X": 0.8041268587112427, "Y": 0.6862218976020813},
                            {"X": 0.8457481861114502, "Y": 0.6862016320228577},
                            {"X": 0.8457596302032471, "Y": 0.6992347240447998},
                            {"X": 0.8041381239891052, "Y": 0.6992548704147339},
                        ],
                    },
                    "Id": "b5bf66b1-4719-44ee-8e92-7d838e0542a6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97467803955078,
                    "Text": "a",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0128448735922575,
                            "Height": 0.010010473430156708,
                            "Left": 0.8529848456382751,
                            "Top": 0.6893817782402039,
                        },
                        "Polygon": [
                            {"X": 0.8529848456382751, "Y": 0.6893880367279053},
                            {"X": 0.8658208250999451, "Y": 0.6893817782402039},
                            {"X": 0.8658297061920166, "Y": 0.6993860602378845},
                            {"X": 0.8529936671257019, "Y": 0.6993922591209412},
                        ],
                    },
                    "Id": "e602b286-17cb-4d60-890e-525775711a5c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.52693939208984,
                    "Text": "poll",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.03592218458652496,
                            "Height": 0.01629442721605301,
                            "Left": 0.8730247020721436,
                            "Top": 0.6862525343894958,
                        },
                        "Polygon": [
                            {"X": 0.8730247020721436, "Y": 0.686269998550415},
                            {"X": 0.9089322090148926, "Y": 0.6862525343894958},
                            {"X": 0.9089469313621521, "Y": 0.7025296092033386},
                            {"X": 0.873039186000824, "Y": 0.7025469541549683},
                        ],
                    },
                    "Id": "936fc403-f279-4e6d-bc95-9e112da3d5f7",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97886657714844,
                    "Text": "to",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.01964408904314041,
                            "Height": 0.012053346261382103,
                            "Left": 0.9153161644935608,
                            "Top": 0.6871861815452576,
                        },
                        "Polygon": [
                            {"X": 0.9153161644935608, "Y": 0.6871957182884216},
                            {"X": 0.9349492788314819, "Y": 0.6871861815452576},
                            {"X": 0.9349602460861206, "Y": 0.6992300152778625},
                            {"X": 0.9153270125389099, "Y": 0.6992395520210266},
                        ],
                    },
                    "Id": "f599f9cf-d136-4bf0-99db-a2ac608e743c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99404907226562,
                    "Text": "be",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.025250466540455818,
                            "Height": 0.012949913740158081,
                            "Left": 0.060459546744823456,
                            "Top": 0.7055171728134155,
                        },
                        "Polygon": [
                            {
                                "X": 0.060459546744823456,
                                "Y": 0.7055293917655945,
                            },
                            {"X": 0.08570203930139542, "Y": 0.7055171728134155},
                            {"X": 0.08571001142263412, "Y": 0.7184549570083618},
                            {"X": 0.06046740338206291, "Y": 0.718467116355896},
                        ],
                    },
                    "Id": "81fc0038-f432-4eac-840d-a9f170b3f4e1",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99403381347656,
                    "Text": "held",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.043679315596818924,
                            "Height": 0.013056310825049877,
                            "Left": 0.09349009394645691,
                            "Top": 0.7053595781326294,
                        },
                        "Polygon": [
                            {"X": 0.09349009394645691, "Y": 0.7053807377815247},
                            {"X": 0.13716115057468414, "Y": 0.7053595781326294},
                            {"X": 0.13716940581798553, "Y": 0.7183948755264282},
                            {"X": 0.09349815547466278, "Y": 0.7184159159660339},
                        ],
                    },
                    "Id": "e79b13a9-0dd3-47ad-ba67-84e1392cb151",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98739624023438,
                    "Text": "on",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.025163140147924423,
                            "Height": 0.010013758204877377,
                            "Left": 0.14427286386489868,
                            "Top": 0.7083317637443542,
                        },
                        "Polygon": [
                            {"X": 0.14427286386489868, "Y": 0.7083439230918884},
                            {"X": 0.16942955553531647, "Y": 0.7083317637443542},
                            {"X": 0.1694360077381134, "Y": 0.71833336353302},
                            {"X": 0.14427922666072845, "Y": 0.7183455228805542},
                        ],
                    },
                    "Id": "571f3dfb-f819-498d-b996-59ce3a70408e",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9887466430664,
                    "Text": "Thursday",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.1063103973865509,
                            "Height": 0.016482891514897346,
                            "Left": 0.17626191675662994,
                            "Top": 0.7052664756774902,
                        },
                        "Polygon": [
                            {"X": 0.17626191675662994, "Y": 0.7053178548812866},
                            {"X": 0.2825610637664795, "Y": 0.7052664756774902},
                            {"X": 0.28257229924201965, "Y": 0.7216982245445251},
                            {"X": 0.17627254128456116, "Y": 0.7217493653297424},
                        ],
                    },
                    "Id": "58b78454-bbcb-43b7-bed1-755328f08704",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96733856201172,
                    "Text": "9",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.012869853526353836,
                            "Height": 0.012987621128559113,
                            "Left": 0.2892302870750427,
                            "Top": 0.705634593963623,
                        },
                        "Polygon": [
                            {"X": 0.2892302870750427, "Y": 0.7056407928466797},
                            {"X": 0.30209118127822876, "Y": 0.705634593963623},
                            {"X": 0.30210015177726746, "Y": 0.7186160087585449},
                            {"X": 0.28923919796943665, "Y": 0.7186222076416016},
                        ],
                    },
                    "Id": "00ae46e1-b874-4918-bd56-8e3ecea93730",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 94.30254364013672,
                    "Text": "November,",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.11960066854953766,
                            "Height": 0.01563774235546589,
                            "Left": 0.3096878230571747,
                            "Top": 0.7051196694374084,
                        },
                        "Polygon": [
                            {"X": 0.3096878230571747, "Y": 0.7051775455474854},
                            {"X": 0.4292770326137543, "Y": 0.7051196694374084},
                            {"X": 0.42928847670555115, "Y": 0.7206998467445374},
                            {"X": 0.30969861149787903, "Y": 0.7207574248313904},
                        ],
                    },
                    "Id": "64ab6b41-6732-47f4-bee3-88e582a2564a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9950180053711,
                    "Text": "from",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04683058708906174,
                            "Height": 0.01307316031306982,
                            "Left": 0.4363236129283905,
                            "Top": 0.7052866220474243,
                        },
                        "Polygon": [
                            {"X": 0.4363236129283905, "Y": 0.705309271812439},
                            {"X": 0.4831443727016449, "Y": 0.7052866220474243},
                            {"X": 0.48315420746803284, "Y": 0.7183372378349304},
                            {"X": 0.43633323907852173, "Y": 0.7183597683906555},
                        ],
                    },
                    "Id": "470ae60a-b252-41cb-946f-fe8dec9156e5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98333740234375,
                    "Text": "7am",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04522295668721199,
                            "Height": 0.012744279578328133,
                            "Left": 0.49020975828170776,
                            "Top": 0.705716609954834,
                        },
                        "Polygon": [
                            {"X": 0.49020975828170776, "Y": 0.7057384848594666},
                            {"X": 0.5354229211807251, "Y": 0.705716609954834},
                            {"X": 0.5354326963424683, "Y": 0.7184391021728516},
                            {"X": 0.490219384431839, "Y": 0.7184609174728394},
                        ],
                    },
                    "Id": "0d569fd5-2514-4d73-b59a-0162ece007d5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99323272705078,
                    "Text": "to",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.02032311074435711,
                            "Height": 0.011937599629163742,
                            "Left": 0.5422196984291077,
                            "Top": 0.7064720392227173,
                        },
                        "Polygon": [
                            {"X": 0.5422196984291077, "Y": 0.7064818143844604},
                            {"X": 0.5625334978103638, "Y": 0.7064720392227173},
                            {"X": 0.5625427961349487, "Y": 0.7183998227119446},
                            {"X": 0.5422289371490479, "Y": 0.7184095978736877},
                        ],
                    },
                    "Id": "88b6c374-55eb-426a-8618-c89d6c4850e5",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.88035583496094,
                    "Text": "10pm.",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0630132406949997,
                            "Height": 0.01593446359038353,
                            "Left": 0.5697857141494751,
                            "Top": 0.7056257724761963,
                        },
                        "Polygon": [
                            {"X": 0.5697857141494751, "Y": 0.7056562304496765},
                            {"X": 0.6327860951423645, "Y": 0.7056257724761963},
                            {"X": 0.6327989101409912, "Y": 0.7215299606323242},
                            {"X": 0.5697981715202332, "Y": 0.7215602397918701},
                        ],
                    },
                    "Id": "573d940c-fc64-47c3-8955-d34c39fe2e7e",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98602294921875,
                    "Text": "Dated",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06148877367377281,
                            "Height": 0.013391362503170967,
                            "Left": 0.06110624223947525,
                            "Top": 0.9095040559768677,
                        },
                        "Polygon": [
                            {"X": 0.06110624223947525, "Y": 0.9095318913459778},
                            {"X": 0.12258660793304443, "Y": 0.9095040559768677},
                            {"X": 0.12259501218795776, "Y": 0.9228676557540894},
                            {"X": 0.0611143596470356, "Y": 0.9228954315185547},
                        ],
                    },
                    "Id": "728b5d2f-2373-445f-a206-e83a65ffcb18",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9765625,
                    "Text": "Monday",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.08285417407751083,
                            "Height": 0.01654636114835739,
                            "Left": 0.13028591871261597,
                            "Top": 0.9095830321311951,
                        },
                        "Polygon": [
                            {"X": 0.13028591871261597, "Y": 0.9096205830574036},
                            {"X": 0.2131291925907135, "Y": 0.9095830321311951},
                            {"X": 0.2131400853395462, "Y": 0.9260920286178589},
                            {"X": 0.13029633462429047, "Y": 0.9261293411254883},
                        ],
                    },
                    "Id": "d5c55ef7-037c-466c-b956-138875c316c0",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.96540069580078,
                    "Text": "16",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.024331755936145782,
                            "Height": 0.012998041696846485,
                            "Left": 0.22146464884281158,
                            "Top": 0.9099513292312622,
                        },
                        "Polygon": [
                            {"X": 0.22146464884281158, "Y": 0.9099623560905457},
                            {"X": 0.24578768014907837, "Y": 0.9099513292312622},
                            {"X": 0.24579639732837677, "Y": 0.9229384064674377},
                            {"X": 0.22147326171398163, "Y": 0.9229493737220764},
                        ],
                    },
                    "Id": "f681e108-cdc7-40d5-b506-98018ce6c742",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97468566894531,
                    "Text": "October",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0842636376619339,
                            "Height": 0.013163113035261631,
                            "Left": 0.2522628903388977,
                            "Top": 0.9096773266792297,
                        },
                        "Polygon": [
                            {"X": 0.2522628903388977, "Y": 0.909715473651886},
                            {"X": 0.3365173041820526, "Y": 0.9096773266792297},
                            {"X": 0.3365265130996704, "Y": 0.9228023886680603},
                            {"X": 0.25227174162864685, "Y": 0.922840416431427},
                        ],
                    },
                    "Id": "5678b13f-0f2f-4756-8df4-7c6e7fa5792f",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99127960205078,
                    "Text": "2023",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05189570412039757,
                            "Height": 0.012939807027578354,
                            "Left": 0.3426361083984375,
                            "Top": 0.9099482893943787,
                        },
                        "Polygon": [
                            {"X": 0.3426361083984375, "Y": 0.9099718332290649},
                            {"X": 0.394522488117218, "Y": 0.9099482893943787},
                            {"X": 0.39453181624412537, "Y": 0.9228646755218506},
                            {"X": 0.34264522790908813, "Y": 0.9228881001472473},
                        ],
                    },
                    "Id": "85dffc5a-2c30-48e8-b9cb-333588886952",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9176254272461,
                    "Text": "Jennifer",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0837274119257927,
                            "Height": 0.013066873885691166,
                            "Left": 0.7044743299484253,
                            "Top": 0.909684419631958,
                        },
                        "Polygon": [
                            {"X": 0.7044743299484253, "Y": 0.9097223281860352},
                            {"X": 0.7881905436515808, "Y": 0.909684419631958},
                            {"X": 0.7882017493247986, "Y": 0.9227135181427002},
                            {"X": 0.7044851183891296, "Y": 0.9227513074874878},
                        ],
                    },
                    "Id": "a2f29f81-c89d-4bca-b65f-f54e224bff5a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.83576965332031,
                    "Text": "Daothong",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.10067856311798096,
                            "Height": 0.01667926087975502,
                            "Left": 0.7957570552825928,
                            "Top": 0.9095743894577026,
                        },
                        "Polygon": [
                            {"X": 0.7957570552825928, "Y": 0.9096200466156006},
                            {"X": 0.8964206576347351, "Y": 0.9095743894577026},
                            {"X": 0.8964356184005737, "Y": 0.9262083172798157},
                            {"X": 0.7957713603973389, "Y": 0.9262536764144897},
                        ],
                    },
                    "Id": "e3565e3f-b539-45d3-b24a-137c7cc9e7d1",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97314453125,
                    "Text": "Returning",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.10005182772874832,
                            "Height": 0.0163221824914217,
                            "Left": 0.7201768755912781,
                            "Top": 0.9289615154266357,
                        },
                        "Polygon": [
                            {"X": 0.7201768755912781, "Y": 0.9290065765380859},
                            {"X": 0.8202145099639893, "Y": 0.9289615154266357},
                            {"X": 0.8202286958694458, "Y": 0.9452388882637024},
                            {"X": 0.7201904654502869, "Y": 0.9452837109565735},
                        ],
                    },
                    "Id": "21b02bee-df70-44bb-82a9-fe870871ffd3",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.97240447998047,
                    "Text": "Officer",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.06895715743303299,
                            "Height": 0.013462814502418041,
                            "Left": 0.8281788229942322,
                            "Top": 0.928695559501648,
                        },
                        "Polygon": [
                            {"X": 0.8281788229942322, "Y": 0.9287266135215759},
                            {"X": 0.8971239328384399, "Y": 0.928695559501648},
                            {"X": 0.8971359729766846, "Y": 0.9421274662017822},
                            {"X": 0.8281905651092529, "Y": 0.9421584010124207},
                        ],
                    },
                    "Id": "2d4bbbb1-a2cb-4855-a269-fc51120b5cda",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99054718017578,
                    "Text": "Printed",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.042497508227825165,
                            "Height": 0.007815025746822357,
                            "Left": 0.18190988898277283,
                            "Top": 0.9658861756324768,
                        },
                        "Polygon": [
                            {"X": 0.18190988898277283, "Y": 0.9659050703048706},
                            {"X": 0.22440221905708313, "Y": 0.9658861756324768},
                            {"X": 0.2244073897600174, "Y": 0.9736823439598083},
                            {"X": 0.18191494047641754, "Y": 0.9737011790275574},
                        ],
                    },
                    "Id": "bd84b4c2-2101-4583-b26a-c20b19d5be88",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99279022216797,
                    "Text": "and",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.02236328460276127,
                            "Height": 0.007673971820622683,
                            "Left": 0.22819161415100098,
                            "Top": 0.9659726619720459,
                        },
                        "Polygon": [
                            {"X": 0.22819161415100098, "Y": 0.9659825563430786},
                            {"X": 0.2505497336387634, "Y": 0.9659726619720459},
                            {"X": 0.2505548894405365, "Y": 0.9736366868019104},
                            {"X": 0.22819671034812927, "Y": 0.9736465811729431},
                        ],
                    },
                    "Id": "ca3c5440-61e6-4404-b38d-8c3b898cbc00",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.9681625366211,
                    "Text": "published",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05741288885474205,
                            "Height": 0.009620015509426594,
                            "Left": 0.2542211413383484,
                            "Top": 0.96592777967453,
                        },
                        "Polygon": [
                            {"X": 0.2542211413383484, "Y": 0.9659533500671387},
                            {"X": 0.3116273581981659, "Y": 0.96592777967453},
                            {"X": 0.31163403391838074, "Y": 0.9755223393440247},
                            {"X": 0.2542276084423065, "Y": 0.9755477905273438},
                        ],
                    },
                    "Id": "c26939ce-b606-426f-a33b-bb31a840c27a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.98832702636719,
                    "Text": "by",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.014159196056425571,
                            "Height": 0.00949681643396616,
                            "Left": 0.3154996931552887,
                            "Top": 0.9659340977668762,
                        },
                        "Polygon": [
                            {"X": 0.3154996931552887, "Y": 0.9659404158592224},
                            {"X": 0.32965224981307983, "Y": 0.9659340977668762},
                            {"X": 0.3296588957309723, "Y": 0.9754246473312378},
                            {"X": 0.31550630927085876, "Y": 0.9754309058189392},
                        ],
                    },
                    "Id": "e195cc68-1355-4975-95c2-766f26963800",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.99707794189453,
                    "Text": "the",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.018994852900505066,
                            "Height": 0.007620286662131548,
                            "Left": 0.33298882842063904,
                            "Top": 0.9661027789115906,
                        },
                        "Polygon": [
                            {"X": 0.33298882842063904, "Y": 0.9661111831665039},
                            {"X": 0.35197827219963074, "Y": 0.9661027789115906},
                            {"X": 0.3519836664199829, "Y": 0.9737145900726318},
                            {"X": 0.33299416303634644, "Y": 0.9737230539321899},
                        ],
                    },
                    "Id": "b8654b64-189a-4954-898d-f9c8edee9c8d",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.95829772949219,
                    "Text": "Returning",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05760706588625908,
                            "Height": 0.009670679457485676,
                            "Left": 0.3562362790107727,
                            "Top": 0.9659144282341003,
                        },
                        "Polygon": [
                            {"X": 0.3562362790107727, "Y": 0.9659400582313538},
                            {"X": 0.4138363003730774, "Y": 0.9659144282341003},
                            {"X": 0.4138433337211609, "Y": 0.9755595326423645},
                            {"X": 0.3562431037425995, "Y": 0.9755851030349731},
                        ],
                    },
                    "Id": "9d0312ff-f743-47d2-9107-d840f76a362e",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.74888610839844,
                    "Text": "Officer,",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04451318457722664,
                            "Height": 0.00910960789769888,
                            "Left": 0.4173152446746826,
                            "Top": 0.9655815958976746,
                        },
                        "Polygon": [
                            {"X": 0.4173152446746826, "Y": 0.96560138463974},
                            {"X": 0.46182164549827576, "Y": 0.9655815958976746},
                            {"X": 0.46182844042778015, "Y": 0.9746714234352112},
                            {"X": 0.4173218905925751, "Y": 0.9746912121772766},
                        ],
                    },
                    "Id": "55e522a6-848c-4aa5-94c8-fc3532f464f6",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.92587280273438,
                    "Text": "Ground",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.045443590730428696,
                            "Height": 0.008356111124157906,
                            "Left": 0.4639911651611328,
                            "Top": 0.9657019376754761,
                        },
                        "Polygon": [
                            {"X": 0.4639911651611328, "Y": 0.9657221436500549},
                            {"X": 0.5094283819198608, "Y": 0.9657019376754761},
                            {"X": 0.5094347596168518, "Y": 0.9740378856658936},
                            {"X": 0.46399739384651184, "Y": 0.9740580320358276},
                        ],
                    },
                    "Id": "77812498-fe7d-47ee-8855-7c750214948c",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.78559112548828,
                    "Text": "Floor,",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.033403318375349045,
                            "Height": 0.008916910737752914,
                            "Left": 0.513647735118866,
                            "Top": 0.9659700989723206,
                        },
                        "Polygon": [
                            {"X": 0.513647735118866, "Y": 0.9659849405288696},
                            {"X": 0.5470441579818726, "Y": 0.9659700989723206},
                            {"X": 0.5470510125160217, "Y": 0.9748721718788147},
                            {"X": 0.5136545300483704, "Y": 0.9748870134353638},
                        ],
                    },
                    "Id": "92ace678-ce10-4b00-aac0-05f362479b64",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.70680236816406,
                    "Text": "Laurence",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.05592365935444832,
                            "Height": 0.007762436289340258,
                            "Left": 0.5514752268791199,
                            "Top": 0.9659815430641174,
                        },
                        "Polygon": [
                            {"X": 0.5514752268791199, "Y": 0.9660063982009888},
                            {"X": 0.6073927283287048, "Y": 0.9659815430641174},
                            {"X": 0.6073988676071167, "Y": 0.9737191796302795},
                            {"X": 0.5514812469482422, "Y": 0.9737439751625061},
                        ],
                    },
                    "Id": "9729c48e-8197-49c0-9c86-97a20ce12e6a",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 99.80924987792969,
                    "Text": "House,",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04171324148774147,
                            "Height": 0.008792084641754627,
                            "Left": 0.6114765405654907,
                            "Top": 0.9659830331802368,
                        },
                        "Polygon": [
                            {"X": 0.6114765405654907, "Y": 0.966001570224762},
                            {"X": 0.6531826853752136, "Y": 0.9659830331802368},
                            {"X": 0.6531897783279419, "Y": 0.9747565984725952},
                            {"X": 0.6114835739135742, "Y": 0.9747750759124756},
                        ],
                    },
                    "Id": "277107d2-8266-471d-a575-c726c7a190f1",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.97391510009766,
                    "Text": "Catford,",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04711008816957474,
                            "Height": 0.008913666009902954,
                            "Left": 0.6576790809631348,
                            "Top": 0.9658103585243225,
                        },
                        "Polygon": [
                            {"X": 0.6576790809631348, "Y": 0.9658313393592834},
                            {"X": 0.7047818303108215, "Y": 0.9658103585243225},
                            {"X": 0.7047892212867737, "Y": 0.9747031331062317},
                            {"X": 0.6576863527297974, "Y": 0.9747240543365479},
                        ],
                    },
                    "Id": "4ca33f52-9d02-4631-b770-30305278cbe4",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.82167053222656,
                    "Text": "London,",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.04776584357023239,
                            "Height": 0.008609703741967678,
                            "Left": 0.7090970873832703,
                            "Top": 0.9660375714302063,
                        },
                        "Polygon": [
                            {"X": 0.7090970873832703, "Y": 0.9660588502883911},
                            {"X": 0.7568556666374207, "Y": 0.9660375714302063},
                            {"X": 0.7568629384040833, "Y": 0.9746261239051819},
                            {"X": 0.7091042399406433, "Y": 0.9746472835540771},
                        ],
                    },
                    "Id": "0fcc9633-8319-4aee-9ad6-af62f6a1d0db",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 97.73977661132812,
                    "Text": "SE6",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.025475656613707542,
                            "Height": 0.0079053258523345,
                            "Left": 0.7612534165382385,
                            "Top": 0.9658412933349609,
                        },
                        "Polygon": [
                            {"X": 0.7612534165382385, "Y": 0.9658526182174683},
                            {"X": 0.7867223024368286, "Y": 0.9658412933349609},
                            {"X": 0.786729097366333, "Y": 0.9737353324890137},
                            {"X": 0.7612601518630981, "Y": 0.9737465977668762},
                        ],
                    },
                    "Id": "79ee1c09-6875-45cb-a3df-7ea7dbbd0cdb",
                    "Page": 1,
                },
                {
                    "BlockType": "WORD",
                    "Confidence": 98.50249481201172,
                    "Text": "4RU",
                    "TextType": "PRINTED",
                    "Geometry": {
                        "BoundingBox": {
                            "Width": 0.0271504744887352,
                            "Height": 0.007787633221596479,
                            "Left": 0.7900754809379578,
                            "Top": 0.9658713340759277,
                        },
                        "Polygon": [
                            {"X": 0.7900754809379578, "Y": 0.9658833742141724},
                            {"X": 0.8172191977500916, "Y": 0.9658713340759277},
                            {"X": 0.8172259330749512, "Y": 0.9736469388008118},
                            {"X": 0.7900821566581726, "Y": 0.9736589789390564},
                        ],
                    },
                    "Id": "61e54dce-a241-4eff-93e2-6fc38e3a021e",
                    "Page": 1,
                },
            ],
            "DetectDocumentTextModelVersion": "1.0",
        },
        analysis_status="SUCCEEDED",
    )
    yield TextractSOPNParsingHelper(
        official_document=official_document, textract_result=textract_result
    )


def test_create_df_from_textract_result(textract_sopn_parsing_helper):
    # assert that get_rows_columns_map is called once
    df = textract_sopn_parsing_helper.create_df_from_textract_result(
        official_document=textract_sopn_parsing_helper.official_document,
        textract_result=textract_sopn_parsing_helper.textract_result,
    )

    sopn_text = "STATEMENT OF PERSONS"
    assert sopn_text in df.values


class MyS3Client:
    def __init__(self, region_name="eu-west-2"):
        self.client = boto3.client("s3", region_name=region_name)

    def list_buckets(self):
        """Returns a list of bucket names."""
        response = self.client.list_buckets()
        return [bucket["Name"] for bucket in response["Buckets"]]

    def list_objects(self, bucket_name, prefix):
        """Returns a list all objects with specified prefix."""
        response = self.client.list_objects(
            Bucket=bucket_name,
            Prefix=prefix,
        )
        return [object["Key"] for object in response["Contents"]]
