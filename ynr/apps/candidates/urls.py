from django.conf import settings
from django.conf.urls import include, url
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

import candidates.views as views

from .feeds import NeedsReviewFeed, RecentChangesFeed

urlpatterns = [
    url(
        r"^api-auth/",
        include("rest_framework.urls", namespace="rest_framework"),
    ),
    url(r"^", include(settings.ELECTION_APP_FULLY_QUALIFIED + ".urls")),
    url(
        r"^election/(?P<ballot_paper_id>[^/]+)/record-winner$",
        views.ConstituencyRecordWinnerView.as_view(),
        name="record-winner",
    ),
    url(
        r"^election/(?P<ballot_paper_id>[^/]+)/retract-winner$",
        views.ConstituencyRetractWinnerView.as_view(),
        name="retract-winner",
    ),
    url(  # Rename to CandidacyCreateView
        r"^election/(?P<ballot_paper_id>[^/]+)/candidacy$",
        views.CandidacyView.as_view(),
        name="candidacy-create",
    ),
    url(
        r"^election/(?P<ballot_paper_id>[^/]+)/candidacy/delete$",
        views.CandidacyDeleteView.as_view(),
        name="candidacy-delete",
    ),
    url(
        r"^election/(?P<ballot_paper_id>[^/]+)/person/create/$",
        views.NewPersonView.as_view(),
        name="person-create",
    ),
    url(
        r"^update-disallowed$",
        TemplateView.as_view(template_name="candidates/update-disallowed.html"),
        name="update-disallowed",
    ),

    # General views across the site (move to a "core" type app?)
    url(
        r"^all-edits-disallowed$",
        TemplateView.as_view(
            template_name="candidates/all-edits-disallowed.html"
        ),
        name="all-edits-disallowed",
    ),
    url(
        r"^recent-changes$",
        views.RecentChangesView.as_view(),
        name="recent-changes",
    ),
    url(r"^leaderboard$", views.LeaderboardView.as_view(), name="leaderboard"),
    url(
        r"^leaderboard/contributions.csv$",
        views.UserContributions.as_view(),
        name="user-contributions",
    ),
    url(r"^feeds/changes.xml$", RecentChangesFeed(), name="changes_feed"),
    url(
        r"^feeds/needs-review.xml$", NeedsReviewFeed(), name="needs-review_feed"
    ),
    url(
        r"^help/api$",
        RedirectView.as_view(url="/api/", permanent=True),
        name="help-api",
    ),
    url(
        r"^help/results$", views.HelpResultsView.as_view(), name="help-results"
    ),
    url(r"^help/about$", views.HelpAboutView.as_view(), name="help-about"),
    url(
        r"^help/privacy$",
        RedirectView.as_view(
            url="https://democracyclub.org.uk/privacy/", permanent=True
        ),
        name="help-privacy",
    ),
    url(
        r"^help/photo-policy$",
        TemplateView.as_view(template_name="candidates/photo-policy.html"),
        name="help-photo-policy",
    ),
    url(
        r"^copyright-question$",
        views.AskForCopyrightAssigment.as_view(),
        name="ask-for-copyright-assignment",
    ),
    # ----------------- Legacy redirect views
    url(
        r"^areas/(?P<type_and_area_ids>.*?)(?:/(?P<ignored_slug>.*))?$",
        views.AreasView.as_view(),
        name="areas-view",
    ),
    url(
        r"^posts-of-type/(?P<post_type>.*?)(?:/(?P<ignored_slug>.*))?$",
        views.PostsOfTypeView.as_view(),
        name="posts-of-type-view",
    ),
]

urlpatterns += [
    url(r"^numbers/", include("cached_counts.urls")),
    url(r"^moderation/", include("moderation_queue.urls")),
]
