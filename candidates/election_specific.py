from django.conf import settings

# This is actually taken from Pombola's country-specific code package
# in pombola/country/__init__.py. You should add to this list anything
# country-specific you want to be available through an import from
# candidates.election_specific

imports_and_defaults = (
    ('MapItData', None),
    ('PartyData', None),
    ('AreaPostData', None),
)

# Note that one could do this without the dynamic import and use of
# globals() by switching on country names and importing * from each
# country specific module, as MapIt does. [1] I slightly prefer the
# version here since you can explicitly list the names to be imported,
# and provide a default value.
#
# [1] https://github.com/mysociety/mapit/blob/master/mapit/countries/__init__.py

for name_to_import, default_value in imports_and_defaults:
    if settings.ELECTION_APP:
        try:
            globals()[name_to_import] = \
                getattr(
                    __import__(
                        settings.ELECTION_APP_FULLY_QUALIFIED + '.lib',
                        fromlist=[name_to_import]
                    ),
                    name_to_import
                )
        except (ImportError, AttributeError):
            globals()[name_to_import] = default_value
    else:
        globals()[name_to_import] = default_value

MAPIT_DATA = MapItData()
PARTY_DATA = PartyData()
AREA_POST_DATA = AreaPostData(MAPIT_DATA, PARTY_DATA)
