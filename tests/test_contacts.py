"""The contacts rules, as tests. Every business, address and page here is invented; nothing touches the
network or a browser."""
import pytest

import contacts

SITE = "https://www.harbourlinesalon.example/"


# --- emails ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("mailto:Hello@HarbourlineSalon.example?subject=Booking", "hello@harbourlinesalon.example"),
    ("mailto:%20info@harbourlinesalon.example", "info@harbourlinesalon.example"),
    ("(frontdesk@harbourlinesalon.example).", "frontdesk@harbourlinesalon.example"),
])
def test_an_address_is_taken_as_published_minus_its_wrapping(raw, expected):
    assert contacts.clean_email(raw) == expected


@pytest.mark.parametrize("junk", [
    "logo@2x.png", "hero-image@harbourline.jpg", "605a7baede844d278b89dc95ae0a9123@sentry.wixpress.com",
    "info@example.com", "yourname@harbourlinesalon.example", "name@harbourlinesalon.example", "user@domain.com",
    "not-an-address", "",
])
def test_junk_is_never_an_address(junk):
    assert contacts.clean_email(junk) == ""


def test_a_mailto_link_outranks_the_same_address_as_text_and_each_keeps_its_page():
    page = SITE + "contact"
    found = contacts.emails_on_page(page, ["mailto:hello@harbourlinesalon.example"],
                                    "Write to hello@harbourlinesalon.example or bookings@harbourlinesalon.example. logo@2x.png")
    assert found == {"hello@harbourlinesalon.example": {"page": page, "how": "mailto"},
                     "bookings@harbourlinesalon.example": {"page": page, "how": "text"}}


def test_the_sites_own_domain_comes_first_then_free_mail_then_anything_else_flagged():
    page = {"page": SITE, "how": "text"}
    own = {"studio@harbourlinesalon.example": page, "harbourline@gmail.com": page, "admin@parentgroup.example": page}
    assert contacts.pick_email(own, SITE) == ("studio@harbourlinesalon.example", "")
    assert contacts.pick_email({"harbourline@gmail.com": page, "admin@parentgroup.example": page}, SITE)[0] == "harbourline@gmail.com"
    best, note = contacts.pick_email({"admin@parentgroup.example": page}, SITE)
    assert best == "admin@parentgroup.example" and "another domain" in note
    assert contacts.pick_email({"careers@harbourlinesalon.example": page, "hello@harbourlinesalon.example": page},
                               SITE)[0] == "hello@harbourlinesalon.example"
    assert contacts.pick_email({}, SITE) == ("", "")


# --- Facebook and Instagram -------------------------------------------------------------------------

@pytest.mark.parametrize("href, expected", [
    ("https://www.facebook.com/HarbourlineSalon/?fref=ts", "https://www.facebook.com/HarbourlineSalon/"),
    ("https://facebook.com/harbourlinesalon", "https://facebook.com/harbourlinesalon"),
    ("https://www.facebook.com/profile.php?id=100012345678901&ref=bookmarks",
     "https://www.facebook.com/profile.php?id=100012345678901"),
    ("https://www.facebook.com/Harbourline-Salon-126147967400642/", "https://www.facebook.com/Harbourline-Salon-126147967400642/"),
    ("https://www.instagram.com/harbourline.salon/?hl=en", "https://www.instagram.com/harbourline.salon/"),
    ("https://instagram.com/harbourlinesalon?igshid=NzZlODBkYWE4Ng==", "https://instagram.com/harbourlinesalon"),
])
def test_a_business_page_is_kept_as_published_minus_its_query_string(href, expected):
    assert contacts.profile_url(href) == (expected, "")


@pytest.mark.parametrize("href, why", [
    ("https://www.facebook.com/sharer/sharer.php?u=https://harbourlinesalon.example", "share button"),
    ("https://www.facebook.com/share.php?u=x", "share button"),
    ("https://www.facebook.com/dialog/share?app_id=1", "share button"),
    ("https://www.facebook.com/plugins/page.php?href=x", "share button"),
    ("https://www.facebook.com/", "home page"),
    ("https://www.facebook.com/pg/harbourlinesalon/reviews", "tab of a page"),
    ("https://www.facebook.com/wix", "platform account"),
    ("https://www.facebook.com/profile.php", "no page id"),
    ("https://www.instagram.com/p/DZVchmSMsgS/", "post"),
    ("https://www.instagram.com/reel/DBe37DbpTTD/", "post"),
    ("https://www.instagram.com/explore/tags/harbourline/", "post"),
    ("https://www.instagram.com/harbourlinesalon/reel/DYtB7Dlpijl/", "inside an account"),
    ("https://www.instagram.com/", "home page"),
    ("https://www.instagram.com/glossgenius", "platform account"),
    ("https://www.harbourlinesalon.example/facebook", "not a Facebook or Instagram link"),
])
def test_share_buttons_posts_platform_accounts_and_home_pages_are_not_business_pages(href, why):
    url, reason = contacts.profile_url(href)
    assert url == "" and why in reason


def test_links_on_a_page_are_kept_with_their_position_and_rejected_ones_with_the_reason():
    found = contacts.socials_on_page(SITE, [
        ("https://www.facebook.com/harbourlinesalon", "Facebook", "footer"),
        ("https://www.facebook.com/sharer/sharer.php?u=x", "Share", "body"),
        ("https://www.harbourlinesalon.example/about", "About", "header"),
    ])
    assert [(f["kind"], f["url"], f["where"]) for f in found] == [
        ("facebook", "https://www.facebook.com/harbourlinesalon", "footer"), ("facebook", "", "body")]
    assert "share button" in found[1]["rejected"]


def link(url, where, page=SITE):
    return {"kind": "instagram", "url": url, "where": where, "page": page}


def test_the_header_or_footer_account_beats_the_stylists_in_the_body():
    candidates = [link("https://www.instagram.com/stylist.one", "body", SITE + "team"),
                  link("https://www.instagram.com/harbourlinesalon/", "header"),
                  link("https://www.instagram.com/harbourlinesalon", "footer"),
                  link("https://www.instagram.com/stylist.two", "body", SITE + "team")]
    url, chosen, note = contacts.pick_profile(candidates, "Harbourline Salon", SITE)
    assert url == "https://www.instagram.com/harbourlinesalon/" and chosen["where"] == "header" and note == ""


def test_the_listings_own_link_comes_first():
    candidates = [link("https://www.instagram.com/harbourlinesalon", "footer"),
                  link("https://www.instagram.com/harbourline.official", "listing", "Google Maps listing (its website link)")]
    assert contacts.pick_profile(candidates, "Harbourline Salon", "")[0] == "https://www.instagram.com/harbourline.official"


def test_several_location_pages_are_settled_by_the_business_name_or_left_blank():
    pages = [link(f"https://www.facebook.com/{handle}", "body") for handle in
             ("HarbourlineSalon", "HarbourlineSalonWestEnd", "harbourlinesalonnorthgate")]
    url, _, note = contacts.pick_profile(pages, "Harbourline Salon West End", SITE)
    assert url == "https://www.facebook.com/HarbourlineSalonWestEnd" and "most words" in note
    url, chosen, note = contacts.pick_profile(pages, "Harbourline Salon", SITE)
    assert url == "" and chosen is None and note.startswith("ambiguous: 3")


def test_no_usable_link_means_no_profile():
    assert contacts.pick_profile([{"kind": "facebook", "url": "", "where": "body", "page": SITE}], "Harbourline", SITE) == ("", None, "")


# --- pages that cannot be read -----------------------------------------------------------------------

def test_a_bot_check_a_shown_captcha_or_a_login_is_skipped_and_a_hidden_captcha_frame_is_not():
    assert "bot check" in contacts.gate_reason("Just a moment...", "Checking your browser before accessing.")
    assert "bot check" in contacts.gate_reason("Harbourline", "Please verify you are human to continue.")
    assert contacts.gate_reason("Harbourline Salon", "Book online. " * 200, visible_challenge=True) == "CAPTCHA shown on the page"
    assert contacts.gate_reason("Members", "Sign in to continue", password_field=True) == "login form"
    long_page = "Our services, prices and team. " * 100 + " This form is protected by reCAPTCHA."
    assert contacts.gate_reason("Harbourline Salon", long_page) == ""
    assert contacts.gate_reason("Harbourline Salon", "Book online. " * 200, password_field=True) == ""


def test_only_same_site_contact_pages_are_read_and_never_a_social_page():
    links = [(SITE + "contact-us", "Contact"), (SITE + "about/#team", "About us"), (SITE + "services", "Services"),
             ("https://www.facebook.com/harbourlinesalon", "Contact us on Facebook"),
             ("https://maps.example/harbourline", "Find us"), (SITE + "location", "Visit"), (SITE + "contact-us", "Contact"),
             (SITE + "find-us", "Find us"), (SITE, "Home")]
    assert contacts.contact_pages(links, SITE) == [SITE + "contact-us", SITE + "about/", SITE + "location"]


# --- addresses -------------------------------------------------------------------------------------

def test_a_us_address_splits_into_street_city_state_and_zip():
    assert contacts.split_address("12 Quay Street Ste 3, Harbour City, NJ 07039, United States") == {
        "street": "12 Quay Street Ste 3", "city": "Harbour City", "state": "NJ", "zip": "07039"}
    assert contacts.split_address("Market Hall, 5 Pier Rd, Bayport, FL 33606-1234")["street"] == "Market Hall, 5 Pier Rd"
    assert contacts.split_address("Harbour City, NJ") == {}


def test_a_row_records_the_choice_and_where_it_came_from():
    record = {
        "name": "Harbourline Salon", "category": "Hair salon", "address": "12 Quay St, Harbour City, NJ 07039, United States",
        "phone": "+1 555-010-0199", "website": SITE + "?utm_source=maps", "closed": "", "site_state": "loads (HTTP 200)",
        "emails": {"hello@harbourlinesalon.example": {"page": SITE + "contact", "how": "mailto"}},
        "socials": contacts.socials_on_page(SITE, [("https://www.facebook.com/harbourlinesalon", "", "footer"),
                                                  ("https://www.instagram.com/p/abc/", "", "body")]),
        "maps_url": "https://maps.example/?q=place_id:invented", "checked_at": "2026-10-23T12:00:00+05:00",
    }
    row = contacts.summarise(record)
    assert (row["email"], row["email_page"], row["email_found_as"]) == ("hello@harbourlinesalon.example", SITE + "contact", "mailto")
    assert (row["facebook"], row["facebook_page"], row["instagram"]) == ("https://www.facebook.com/harbourlinesalon", SITE, "")
    assert (row["website"], row["city"], row["state"], row["zip"]) == (SITE, "Harbour City", "NJ", "07039")


def test_a_listing_whose_website_is_a_social_page_gives_that_page_and_no_website():
    record = {"name": "Harbourline Salon", "address": "", "website": "https://www.facebook.com/harbourlinesalon",
              "socials": contacts.socials_on_page("Google Maps listing (its website link)",
                                                  [("https://www.facebook.com/harbourlinesalon", "", "listing")])}
    row = contacts.summarise(record)
    assert row["website"] == "" and row["facebook"] == "https://www.facebook.com/harbourlinesalon"
    assert row["facebook_page"] == "Google Maps listing (its website link)"


def test_an_error_status_is_not_the_site():
    assert contacts.error_status(525) == "error page (HTTP 525)" and contacts.error_status(404) == "error page (HTTP 404)"
    assert contacts.error_status(200) == "" and contacts.error_status(None) == ""


def test_the_sites_domain_is_the_one_it_redirected_to():
    record = {"name": "Harbourline Salon", "address": "", "website": "https://harbourline-salon.example/",
              "home": "https://www.harbourlinesalonnj.example/",
              "emails": {"info@harbourlinesalonnj.example": {"page": "https://www.harbourlinesalonnj.example/", "how": "mailto"}}}
    row = contacts.summarise(record)
    assert row["email"] == "info@harbourlinesalonnj.example" and row["notes"] == ""


def test_a_passing_network_failure_is_tried_again_and_the_sites_own_answer_is_not():
    assert contacts.worth_retrying(None, "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://harbourline.example/")
    assert contacts.worth_retrying(None, "Page.goto: Timeout 60000ms exceeded.")
    assert contacts.worth_retrying(525) and contacts.worth_retrying(503)
    assert not contacts.worth_retrying(404) and not contacts.worth_retrying(200)
    assert not contacts.worth_retrying(None, "Page.goto: net::ERR_CERT_COMMON_NAME_INVALID")
