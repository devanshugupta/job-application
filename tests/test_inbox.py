"""Tests for the inbox command: broad capture + prune tiers, classification
rules, two-gate company matching, threads, no-downgrade transitions, callback
records + Gmail links, idempotency, multi-account handling, IMAP read-safety
(PEEK), calendar invites, needs_reply, and the vouch Callbacks lane. IMAP is
never touched: messages are injected as email.message.Message objects."""

import email
import json

import pytest

from src.tools import inbox, tracker


# ------------------------------------------------------------------ helpers

def make_msg(frm="Someone <someone@example.com>", subject="Hello",
             body="Plain body.", msgid="<m1@mail.example.com>",
             date="Fri, 21 Aug 2026 10:00:00 -0700", html_body=None,
             headers=None, ics=None):
    extra = "".join(f"{k}: {v}\n" for k, v in (headers or {}).items())
    if ics is not None:
        raw = (f"From: {frm}\nSubject: {subject}\nDate: {date}\n"
               f"Message-ID: {msgid}\n{extra}MIME-Version: 1.0\n"
               f'Content-Type: multipart/mixed; boundary="BND"\n\n'
               f"--BND\nContent-Type: text/plain\n\n{body}\n"
               f"--BND\nContent-Type: text/calendar; method=REQUEST\n\n{ics}\n"
               f"--BND--\n")
    elif html_body is not None:
        raw = (f"From: {frm}\nSubject: {subject}\nDate: {date}\n"
               f"Message-ID: {msgid}\n{extra}Content-Type: text/html\n\n{html_body}")
    else:
        raw = (f"From: {frm}\nSubject: {subject}\nDate: {date}\n"
               f"Message-ID: {msgid}\n{extra}Content-Type: text/plain\n\n{body}")
    return email.message_from_string(raw)


def parsed(**kw):
    account = kw.pop("account", "me@x.com")
    return inbox.parse_message(make_msg(**kw), account=account)


ICS = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
       "SUMMARY:Interview with Snowflake\n"
       "DTSTART:20260825T190000Z\n"
       "ORGANIZER;CN=IC:mailto:ic@snowflake.com\n"
       "END:VEVENT\nEND:VCALENDAR")


@pytest.fixture
def inbox_env(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "APPLICATIONS_PATH", tmp_path / "applications.json")
    monkeypatch.setattr(inbox, "SEEN_PATH", tmp_path / "inbox_seen.json")
    for n in ("", "_2"):
        monkeypatch.delenv(f"JOB_AGENT_EMAIL{n}", raising=False)
        monkeypatch.delenv(f"JOB_AGENT_EMAIL_APP_PASSWORD{n}", raising=False)
    return tmp_path


def _run(msgs, **kw):
    return inbox.run_inbox(messages=msgs, **kw)


# ------------------------------------------------------------------ capture

def test_capture_ats_domain():
    assert inbox.broad_capture(parsed(frm="no-reply@ashbyhq.com", body="Hi."), [])


def test_capture_subject_keyword():
    p = parsed(frm="jane@somecorp.com", subject="Your interview with SomeCorp",
               body="Details inside.")
    assert inbox.broad_capture(p, [])


def test_capture_human_recruiter_on_company_domain():
    # The highest-value class: a person at apple.com, no ATS anywhere.
    p = parsed(frm="Courtni Chapin <c_chapin@apple.com>", subject="Friday",
               body="Looking forward to your interview on Friday.")
    assert inbox.broad_capture(p, [])


def test_capture_tracked_company_domain():
    p = parsed(frm="recruiting@snowflake.com", subject="Hello", body="Quick note.")
    assert inbox.broad_capture(p, ["snowflake"])


def test_capture_random_newsletter_fails():
    p = parsed(frm="news@shopdeals.com", subject="50 percent off shoes",
               body="Buy now, big sale this weekend.")
    assert not inbox.broad_capture(p, ["triedge investments"])


def test_freemail_sender_needs_more_than_context():
    # gmail sender talking about "your role" is not captured by the corporate arm
    p = parsed(frm="rando@gmail.com", subject="hi", body="I love my new role.")
    assert not inbox.broad_capture(p, [])


# ------------------------------------------------------------------ prune tiers

def test_alert_linkedin_digest():
    p = parsed(frm="LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
               subject="30 new jobs for machine learning engineer",
               body="Job alert: apply now to these roles matching your search.")
    assert inbox.is_alert(p)


def test_alert_subject_patterns():
    assert inbox.is_alert(parsed(subject="New jobs at Microsoft that match your profile"))
    assert inbox.is_alert(parsed(subject="You've Matched with a Job",
                                 frm="Twilio <notifications@twilio.com>",
                                 body="A job at Twilio matches your profile."))
    assert inbox.is_alert(parsed(subject="Devanshu, this job is a match!"))
    assert inbox.is_alert(parsed(subject="New job opportunities at American Express"))


def test_alert_not_a_real_callback():
    p = parsed(frm="talent@acme.com", subject="Interview with Acme Corp",
               body="Please share your availability.")
    assert not inbox.is_alert(p)


def test_promo_list_unsubscribe():
    p = parsed(frm="IRCTC <offers@irctc.co.in>",
               subject="Exclusive credit card offer inside",
               body="Apply now for the new card.",
               headers={"List-Unsubscribe": "<mailto:u@irctc.co.in>"})
    assert inbox.is_promo(p)


def test_promo_exempts_ats_and_context_subjects():
    assert not inbox.is_promo(parsed(
        frm="no-reply@ashbyhq.com", subject="Weekly digest",
        headers={"List-Unsubscribe": "<mailto:u@a.co>"}))
    assert not inbox.is_promo(parsed(
        frm="talent@acme.com", subject="Your application update",
        headers={"List-Unsubscribe": "<mailto:u@acme.com>"}))


def test_consumer_noise():
    assert inbox.is_consumer_noise(parsed(frm="Uber <uber@uber.com>",
                                          subject="Your Friday trip with Uber"))
    assert inbox.is_consumer_noise(parsed(frm="no.reply.alerts@chase.com",
                                          subject="Transaction alert",
                                          body="A charge on your credit card."))
    assert inbox.is_consumer_noise(parsed(frm="store-news@amazon.com",
                                          subject="Echo deals this week"))
    assert inbox.is_consumer_noise(parsed(frm="payroll@adp.com",
                                          subject="Your pay statement is ready"))


def test_noise_pruned_in_run_even_when_company_tracked(inbox_env):
    tracker.save_application(company="uber", role="SDE", url="http://j/u",
                             status="applied")
    result = _run([make_msg(frm="Uber Receipts <uber@uber.com>",
                            subject="Your Friday trip with Uber",
                            body="Total $14.60", msgid="<r1@uber.com>")])
    assert result["noise"] == 1
    assert not result["groups"] and not result["unmatched"]
    assert tracker.list_applications()[0].get("callbacks") is None


def test_alert_counted_in_run(inbox_env):
    result = _run([make_msg(frm="notifications@twilio.com",
                            subject="You've Matched with a Job",
                            body="A job matches your profile.", msgid="<a1@t.com>")])
    assert result["alerts"] == 1 and not result["groups"]


# ------------------------------------------------------------------ classify

def test_classify_rejected():
    p = parsed(body="Unfortunately we will not be moving forward with your application.")
    assert inbox.classify(p) == "rejected"


def test_classify_interview():
    p = parsed(subject="Phone screen with Acme",
               body="Please share your availability to schedule a phone screen.")
    assert inbox.classify(p) == "interview"


def test_classify_oa():
    p = parsed(subject="Next step: online assessment",
               body="Complete your HackerRank assessment within 5 days.")
    assert inbox.classify(p) == "oa"


def test_classify_offer():
    p = parsed(subject="Your offer", body="We are pleased to offer you the position.")
    assert inbox.classify(p) == "offer"


def test_classify_ack():
    p = parsed(subject="Thanks for applying to Higgsfield !",
               body="We received your application and will review it.")
    assert inbox.classify(p) == "ack"


def test_classify_ack_with_scheduling_is_interview():
    p = parsed(subject="Thanks for applying to Acme",
               body="We received your application. Please schedule your phone screen.")
    assert inbox.classify(p) == "interview"


def test_classify_recruiter_reply():
    p = parsed(subject="Re: your note",
               body="I am the recruiter for this team, happy to discuss next steps.")
    assert inbox.classify(p) == "recruiter_reply"


def test_classify_rejection_beats_interview_wording():
    p = parsed(body="Thank you for taking the time to interview. Unfortunately "
                    "we will not be moving forward.")
    assert inbox.classify(p) == "rejected"


def test_followup_subject_alone_is_not_rejected():
    # Bug 9: ZS "Application follow up" must not be a rejection without
    # rejection LANGUAGE in the body.
    neutral = parsed(subject="Application follow up",
                     body="We are still reviewing your application.")
    assert inbox.classify(neutral) == "recruiter_reply"
    real = parsed(subject="Application follow up",
                  body="Unfortunately we will not be moving forward.")
    assert inbox.classify(real) == "rejected"


def test_classify_vevent_is_interview():
    p = parsed(frm="calendar-notification@google.com",
               subject="Invitation: Interview with Snowflake", ics=ICS)
    assert p["vevent"] and p["dtstart"] == "2026-08-25T19:00Z"
    assert inbox.classify(p) == "interview"


def test_ack_boilerplate_interview_word_stays_ack():
    # Live-lane bug: Docusign/Cloudflare/Lambda acks whose body merely mentions
    # "interview"/"assessment" in boilerplate were classified interview/oa.
    for subject, body in (
        ("Thank you for applying at Docusign",
         "If you are selected for an interview, we will contact you to schedule."),
        ("Cloudflare | Software Engineer Application Received",
         "Our process may include an interview and an online assessment if selected."),
        ("Thank you for applying to Lambda!",
         "We review every application. Interviews are offered to selected candidates."),
    ):
        assert inbox.classify(parsed(subject=subject, body=body)) == "ack", subject


def test_ack_subject_with_real_scheduling_still_interview():
    p = parsed(subject="Thank you for applying to Acme",
               body="Please schedule your phone screen using this link.")
    assert inbox.classify(p) == "interview"


def test_bare_assessment_word_is_not_oa():
    p = parsed(subject="Update on your application",
               body="Our assessment of your background is ongoing.")
    assert inbox.classify(p) != "oa"


def test_dtstart_tzid_and_value_date_and_vtimezone():
    # Live-lane bug: the VTIMEZONE block's DST-rule DTSTART (1970-03-08) was
    # parsed as the meeting time ("Sun Mar 8, 03:00").
    ics = ("BEGIN:VCALENDAR\nBEGIN:VTIMEZONE\nTZID:America/Denver\n"
           "BEGIN:DAYLIGHT\nDTSTART:19700308T020000\nEND:DAYLIGHT\nEND:VTIMEZONE\n"
           "BEGIN:VEVENT\nSUMMARY:Phone Interview\n"
           "DTSTART;TZID=America/Denver:20260824T150000\nEND:VEVENT\nEND:VCALENDAR")
    p = parsed(subject="Phone Interview Confirmation", ics=ics)
    assert p["vevent"] and p["dtstart"] == "2026-08-24T15:00"
    ics2 = ics.replace("DTSTART;TZID=America/Denver:20260824T150000",
                       "DTSTART;VALUE=DATE:20260824")
    assert parsed(subject="Phone Interview Confirmation", ics=ics2)["dtstart"] == "2026-08-24"


def test_past_dtstart_vevent_ignored():
    # An event that starts long before the email was sent is bogus data.
    ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Interview\n"
           "DTSTART:20260601T150000Z\nEND:VEVENT\nEND:VCALENDAR")
    p = parsed(subject="Fwd: notes", body="see attached",
               date="Fri, 21 Aug 2026 10:00:00 -0700", ics=ics)
    assert not p["vevent"] and not p["dtstart"]
    assert inbox.classify(p) != "interview"


def test_cancelled_and_non_interview_vevents_ignored():
    cancel = ICS.replace("BEGIN:VCALENDAR", "BEGIN:VCALENDAR\nMETHOD:CANCEL")
    assert not parsed(subject="Canceled event: Interview", ics=cancel)["vevent"]
    lunch = ICS.replace("SUMMARY:Interview with Snowflake", "SUMMARY:Team lunch")
    assert not parsed(subject="Invitation: Team lunch", ics=lunch)["vevent"]


def test_reprocess_replaces_callback_and_demotes_status(inbox_env):
    # A wrongly-typed interview callback (pre-tightening) must be corrected in
    # place by --reprocess: same msgid replaced, status re-derived (applied).
    tracker.save_application(company="Docusign", role="SWE", url="http://j/rp",
                             status="applied")
    tracker.update_application(
        "http://j/rp", status="interview",
        notes="email 2026-08-19: interview - Thank you for applying at Docusign",
        callbacks=[{"date": "2026-08-19", "type": "interview",
                    "subject": "Thank you for applying at Docusign",
                    "snippet": "s", "msgid": "dc1@docusign.com",
                    "account": "a@x.com", "link": "https://mail.google.com/x"}])
    msg = make_msg(frm="careers@docusign.com",
                   subject="Thank you for applying at Docusign",
                   body="If selected for an interview, we will contact you to schedule.",
                   date="Wed, 19 Aug 2026 10:00:00 -0700", msgid="<dc1@docusign.com>")
    # without --reprocess the seen-file blocks it entirely
    inbox._save_seen({inbox._seen_key("a@x.com", "<dc1@docusign.com>")})
    _run([("a@x.com", msg)])
    row = tracker.list_applications()[0]
    assert row["status"] == "interview"              # untouched, seen
    # with --reprocess: replaced, not appended; status demoted
    _run([("a@x.com", msg)], reprocess=True)
    row = tracker.list_applications()[0]
    assert len(row["callbacks"]) == 1                # replaced, no duplicate
    assert row["callbacks"][0]["type"] == "ack"
    assert row["status"] == "applied"                # stale interview demoted
    assert "ack - Thank you for applying at Docusign" in row["notes"]
    assert "interview - Thank you" not in row["notes"]


def test_reprocess_keeps_supported_status(inbox_env):
    # A row with a REAL interview callback keeps interview through reprocess.
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/rp2",
                             status="applied")
    msg = make_msg(frm="talent@acme.com", subject="Interview with Acme Corp",
                   body="Please schedule your interview.", msgid="<rp2@acme.com>")
    _run([msg])
    assert tracker.list_applications()[0]["status"] == "interview"
    _run([msg], reprocess=True)
    row = tracker.list_applications()[0]
    assert row["status"] == "interview" and len(row["callbacks"]) == 1


def test_latest_callback_is_by_date_not_list_order():
    # Append order is thread-processing order (newest first), so the list tail
    # can be the OLDEST record; the lane and dashboards must pick by date.
    from src.tools import dashboard, focus
    row = {"company": "May Mobility", "role": "SWE II", "url": "u9",
           "status": "rejected",
           "callbacks": [_cb(type="rejected", date="2026-08-20",
                             subject="Regarding your application"),
                         _cb(type="replied", date="2026-08-20", subject="Re: Next"),
                         _cb(type="interview", date="2026-08-17"),
                         _cb(type="ack", date="2026-07-31", subject="Thank you")]}
    latest = focus._latest_cb(row)
    assert latest["type"] == "rejected"     # date-latest; rank breaks the tie
    entries = focus._callback_lane_entries([row])
    assert entries[0][2] == "rejected"      # lane pill from the true latest
    cell = dashboard._callback_cell(row)
    assert "rejected 2026-08-20" in cell


def test_lane_past_dtstart_never_floats():
    from src.tools import focus
    rows = [
        {"company": "Bogus Co", "role": "SWE", "url": "b1", "status": "interview",
         "callbacks": [_cb(type="interview", dtstart="2026-03-08T03:00",
                           date="2026-08-10")]},
        {"company": "Fresh Co", "role": "SWE", "url": "b2", "status": "interview",
         "callbacks": [_cb(type="interview", date="2026-08-21")]},
        {"company": "Agenda Co", "role": "SWE", "url": "b3", "status": "interview",
         "callbacks": [_cb(type="interview", dtstart="2026-08-25T19:00Z",
                           date="2026-08-18")]},
    ]
    order = [e[0]["company"] for e in focus._callback_lane_entries(rows)]
    # future agenda first, then most recent callback date; bogus past date last
    assert order == ["Agenda Co", "Fresh Co", "Bogus Co"]


# ------------------------------------------------------------------ matching

def test_match_ashby_company_in_body(inbox_env):
    tracker.save_application(company="TriEdge Investments", role="AI Engineer",
                             url="http://j/1", status="applied")
    rows = tracker.list_applications()
    p = parsed(frm="TriEdge Investments Hiring Team <no-reply@ashbyhq.com>",
               body="Thank you for applying to TriEdge Investments.")
    assert inbox.match_row(p, rows)["company"] == "TriEdge Investments"
    p2 = parsed(frm="Hiring Team <no-reply@ashbyhq.com>",
                body="Your application to TriEdge Investments was received.")
    assert inbox.match_row(p2, rows)["company"] == "TriEdge Investments"


def test_match_punctuated_company_name(inbox_env):
    tracker.save_application(company="Jack & Jill", role="SDE",
                             url="http://j/2", status="applied")
    p = parsed(frm="talent@jackjill.com",
               body="Hello from the Jack & Jill, Inc. recruiting team.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "Jack & Jill"


def test_match_sender_domain(inbox_env):
    tracker.save_application(company="TriEdge Investments", role="AI Engineer",
                             url="http://j/3", status="applied")
    p = parsed(frm="craig@triedgeinvestments.com", body="Update on your candidacy.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "TriEdge Investments"


def test_match_workday_local_part(inbox_env):
    # Bug 4: nexstar@myworkday.com must match "Nexstar Media Group, Inc".
    tracker.save_application(company="Nexstar Media Group, Inc", role="MLE",
                             url="http://j/nx", status="applied")
    p = parsed(frm="nexstar@myworkday.com", subject="Update",
               body="Thank you for your application.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == \
        "Nexstar Media Group, Inc"


def test_match_ack_subject_extraction(inbox_env):
    # Bug 4: "Thanks for applying to Higgsfield !" -> "Higgsfield AI".
    tracker.save_application(company="Higgsfield AI", role="ML Engineer",
                             url="http://j/hg", status="applied")
    p = parsed(frm="no-reply@ashbyhq.com",
               subject="Thanks for applying to Higgsfield !",
               body="We received your application.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "Higgsfield AI"


def test_match_company_token_in_subject_not_sender_org(inbox_env):
    # "LiteLLM Application Update" sent by "Berrie AI Incorporated" via Ashby.
    tracker.save_application(company="LiteLLM", role="Backend Engineer",
                             url="http://j/ll", status="applied")
    p = parsed(frm="Berrie AI Incorporated <no-reply@ashbyhq.com>",
               subject="LiteLLM Application Update",
               body="An update on your application.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "LiteLLM"


def test_common_word_company_never_matches_body_only(inbox_env):
    # Bug 1: "Driver"/"Current"/"uber" style names need sender/subject evidence.
    tracker.save_application(company="Driver", role="ML Engineer",
                             url="http://j/dr", status="applied")
    p = parsed(frm="recruiter@agency.com", subject="An opportunity",
               body="Our client seeks a driver-focused candidate for this role.")
    assert inbox.match_row(p, tracker.list_applications()) is None
    # but sender/subject evidence still works
    p2 = parsed(frm="talent@driver.com", subject="Driver: interview request",
                body="We would like to schedule an interview.")
    assert inbox.match_row(p2, tracker.list_applications()) is not None


def test_calendar_gateway_domain_is_not_company_evidence(inbox_env):
    tracker.save_application(company="Google", role="SWE", url="http://j/gg",
                             status="applied")
    p = parsed(frm="calendar-notification@google.com",
               subject="Invitation: Interview with Snowflake", ics=ICS)
    assert inbox.match_row(p, tracker.list_applications()) is None


def test_match_role_disambiguation_same_company(inbox_env):
    # Addendum I: two rows at one company -> role-word overlap picks the row.
    tracker.save_application(company="Mercor", role="Software Engineer",
                             url="http://j/m1", status="applied")
    tracker.save_application(company="Mercor", role="Data Analyst",
                             url="http://j/m2", status="applied")
    p = parsed(frm="talent@mercor.com",
               subject="Interview for Data Analyst at Mercor",
               body="Please schedule your interview.")
    assert inbox.match_row(p, tracker.list_applications())["url"] == "http://j/m2"


def test_meeting_platform_body_link_is_not_company_evidence(inbox_env):
    # Real-mail bug: "join via Microsoft Teams" in an Anthuria invite matched
    # the tracked Microsoft row. Platform vendors need sender/subject evidence.
    tracker.save_application(company="Microsoft", role="SWE II",
                             url="http://j/ms", status="applied")
    p = parsed(frm="no-reply@ashbyhq.com",
               subject="Confirmed: Your Upcoming Interview with Anthuria",
               body="Join the interview via Microsoft Teams: https://teams.link")
    assert inbox.match_row(p, tracker.list_applications()) is None
    # subject evidence still attaches fine
    p2 = parsed(frm="talent@microsoft.com",
                subject="Your interview with Microsoft",
                body="Join via Microsoft Teams.")
    assert inbox.match_row(p2, tracker.list_applications()) is not None


def test_subject_evidence_beats_body_only_evidence(inbox_env):
    # Real-mail bug: "Thank you for your interest in Microsoft" attached to a
    # longer-named row whose name only appeared in the body footer.
    tracker.save_application(company="Careers at KKR", role="SWE",
                             url="http://j/kkr", status="found")
    tracker.save_application(company="Microsoft", role="SWE II",
                             url="http://j/ms2", status="applied")
    p = parsed(frm="noreply@careers.microsoft.com",
               subject="Thank you for your interest in Microsoft",
               body="Update on your application. Careers at KKR newsletter footer.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "Microsoft"


def test_workday_short_tenant_local_part(inbox_env):
    # Real-mail bug: hp@myworkday.com could not match the tracked HP row.
    tracker.save_application(company="HP", role="AI Engineer", url="http://j/hp",
                             status="applied")
    p = parsed(frm="hp@myworkday.com", subject="Regarding Requisition AI Engineer",
               body="An update on your job application.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "HP"


def test_ack_variants_do_not_become_replied():
    # Real-mail bug: "We received your job application" / "Thank you for your
    # online submission" were classified recruiter_reply (status applied->replied).
    assert inbox.classify(parsed(
        subject="We received your job application (Job Number: 210774399)",
        body="Your application is in review.")) == "ack"
    assert inbox.classify(parsed(
        subject="Thank you for your online submission",
        body="We appreciate your interest in the position.")) == "ack"


def test_generic_local_part_never_matches_junk_company_row(inbox_env):
    # Real-mail bug: "Careers at KKR" row swallowed every careers@ sender
    # (Twilio, Microsoft, AMD rejections). Generic words are never evidence.
    tracker.save_application(company="Careers at KKR", role="SWE",
                             url="http://j/kk2", status="found")
    tracker.save_application(company="May Mobility", role="SWE II",
                             url="http://j/mm", status="applied")
    p = parsed(frm="May Mobility <careers@maymobility.com>",
               subject="Regarding your application to May Mobility",
               body="An update on your application.")
    assert inbox.match_row(p, tracker.list_applications())["company"] == "May Mobility"
    p2 = parsed(frm="careers@twilio.com",
                subject="Thank you for your interest in Twilio",
                body="We will not be moving forward.")
    assert inbox.match_row(p2, tracker.list_applications()) is None  # Twilio untracked


def test_promo_local_part_substrings(inbox_env):
    # Real-mail bug: irctcpromotions@irctc.co.in escaped the promo tier and its
    # "Complete Your Application" credit-card subject classified as a callback.
    p = parsed(frm="irctcpromotions@irctc.co.in",
               subject="Your IRCTC RBL Bank Credit Card Awaits - Complete Your Application",
               body="Apply now and schedule your card delivery.")
    assert inbox.is_promo(p) or inbox.is_consumer_noise(p)
    result = _run([make_msg(frm="irctcpromotions@irctc.co.in",
                            subject="Your IRCTC RBL Bank Credit Card Awaits - "
                                    "Complete Your Application",
                            body="Apply now and schedule your card delivery.",
                            msgid="<ir1@irctc.co.in>")])
    assert not result["groups"] and not result["unmatched"]


def test_receipt_and_card_subjects_are_noise():
    assert inbox.is_consumer_noise(parsed(
        frm="automated@airbnb.com",
        subject="Confirmed: Your August 15-16 trip, here's your Airbnb receipt"))
    assert inbox.is_consumer_noise(parsed(
        frm="alerts@somebank.com", subject="Your credit card statement"))


def test_no_match_reports_unmatched(inbox_env):
    tracker.save_application(company="Acme", role="SDE", url="http://j/4",
                             status="applied")
    result = _run([make_msg(frm="isabella.childs@snowflake.com",
                            subject="Snowflake - Next Steps",
                            body="We would like to schedule an interview.",
                            msgid="<sf1@snowflake.com>")])
    assert result["unmatched"][0]["classification"] == "interview"


# ------------------------------------------------------------------ end to end

def test_interview_transition_and_callback_shape(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/5",
                             status="applied")
    msg = make_msg(frm="Acme Corp Recruiting <talent@acme.com>",
                   subject="Interview with Acme Corp",
                   body="Please share your availability for a phone screen.",
                   msgid="<iv+1@acme.com>")
    result = _run([("me@asu.edu", msg)])
    row = tracker.list_applications()[0]
    assert row["status"] == "interview"
    assert row["callback_date"] == "2026-08-21"
    assert "email 2026-08-21: interview - Interview with Acme Corp" in row["notes"]
    cb = row["callbacks"][0]
    assert cb["type"] == "interview"
    assert cb["msgid"] == "iv+1@acme.com"            # no angle brackets
    assert cb["account"] == "me@asu.edu"
    assert len(cb["snippet"]) <= 140 and "availability" in cb["snippet"]
    assert cb["link"] == ("https://mail.google.com/mail/?authuser=me%40asu.edu"
                          "#search/rfc822msgid:iv%2B1%40acme.com")
    assert result["groups"]["interview"][0]["account"] == "me@asu.edu"


def test_gmail_link_construction():
    link = inbox.gmail_link("<abc+1@mail.gmail.com>", "me@asu.edu")
    assert link == ("https://mail.google.com/mail/?authuser=me%40asu.edu"
                    "#search/rfc822msgid:abc%2B1%40mail.gmail.com")
    assert inbox.bare_msgid("  <x@y>  ") == "x@y"


def test_ack_recorded_without_status_change(inbox_env):
    # Addendum G: auto-acks are callbacks but never move status.
    tracker.save_application(company="Higgsfield AI", role="MLE", url="http://j/6",
                             status="applied")
    msg = make_msg(frm="no-reply@ashbyhq.com",
                   subject="Thanks for applying to Higgsfield !",
                   body="We received your application.", msgid="<ak1@a.com>")
    result = _run([msg])
    row = tracker.list_applications()[0]
    assert row["status"] == "applied"                # unchanged
    assert row["callbacks"][0]["type"] == "ack"
    assert result["groups"]["ack"][0]["old"] == result["groups"]["ack"][0]["new"]


def test_no_downgrade_ack_keeps_interview(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/7",
                             status="applied")
    tracker.update_application("http://j/7", status="interview")
    msg = make_msg(frm="talent@acme.com", subject="Re: Acme Corp application",
                   body="Thanks, we received your application materials.",
                   msgid="<rr1@acme.com>")
    _run([msg])
    row = tracker.list_applications()[0]
    assert row["status"] == "interview"
    assert "ack" in row["notes"]


def test_rejected_supersedes_interview(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/8",
                             status="applied")
    tracker.update_application("http://j/8", status="interview")
    _run([make_msg(frm="talent@acme.com", subject="Update from Acme Corp",
                   body="Unfortunately we will not be moving forward.",
                   msgid="<rj1@acme.com>")])
    assert tracker.list_applications()[0]["status"] == "rejected"


def test_offer_rows_never_touched(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/9",
                             status="applied", notes="keep")
    tracker.update_application("http://j/9", status="offer")
    _run([make_msg(frm="talent@acme.com", subject="Acme Corp update",
                   body="Unfortunately we will not be moving forward.",
                   msgid="<of1@acme.com>")])
    row = tracker.list_applications()[0]
    assert row["status"] == "offer" and row["notes"] == "keep"
    assert not row.get("callbacks")


def test_generic_mail_never_touches_row(inbox_env):
    # Honesty + bug 5: no pattern -> unclassified -> reported, row untouched.
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/10",
                             status="applied", notes="orig")
    result = _run([make_msg(frm="talent@acme.com", subject="Acme Corp",
                            body="Greetings, an update regarding the position.",
                            msgid="<vg1@acme.com>")])
    row = tracker.list_applications()[0]
    assert row["status"] == "applied" and row["notes"] == "orig"
    assert not row.get("callbacks")
    assert "unclassified" in result["groups"]


def test_stale_email_cannot_change_status(inbox_env):
    # Bug 7: mail older than applied_date is note-only at most.
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/11",
                             status="applied", applied_date="2026-08-01 10:00")
    _run([make_msg(frm="talent@acme.com", subject="Interview with Acme Corp",
                   body="Please schedule your interview.",
                   date="Mon, 20 Jul 2026 09:00:00 -0700", msgid="<st1@acme.com>")])
    row = tracker.list_applications()[0]
    assert row["status"] == "applied"                # not bumped by July mail
    assert row["callbacks"]                          # history still recorded


def test_note_cap_three_per_row_per_run(inbox_env):
    # Bug 5: max 3 note appends per row per run.
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/12",
                             status="applied")
    msgs = [make_msg(frm="talent@acme.com",
                     subject=f"Acme Corp interview step {i}",
                     body="Please schedule your interview.",
                     date=f"Fri, {15 + i} Aug 2026 10:00:00 -0700",
                     msgid=f"<c{i}@acme.com>") for i in range(5)]
    _run(msgs)
    row = tracker.list_applications()[0]
    assert len(row["callbacks"]) == 3
    assert row["notes"].count("email 2026-08-") == 3
    # newest first: the most recent subjects made the cut
    assert any("step 4" in c["subject"] for c in row["callbacks"])


def test_thread_resolves_to_latest_message(inbox_env):
    # Bug 6: a thread's status comes from its LATEST message; one callback.
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/13",
                             status="applied")
    root = make_msg(frm="talent@acme.com", subject="Interview with Acme Corp",
                    body="Please schedule your interview.",
                    date="Mon, 17 Aug 2026 10:00:00 -0700", msgid="<t1@acme.com>")
    reply = make_msg(frm="talent@acme.com", subject="Re: Interview with Acme Corp",
                     body="Unfortunately we will not be moving forward with "
                          "your application.",
                     date="Wed, 19 Aug 2026 10:00:00 -0700", msgid="<t2@acme.com>",
                     headers={"References": "<t1@acme.com>"})
    result = _run([reply, root])   # newest first, as IMAP delivers
    row = tracker.list_applications()[0]
    assert row["status"] == "rejected"
    assert len(row["callbacks"]) == 1
    cb = row["callbacks"][0]
    assert cb["type"] == "rejected" and cb["messages"] == 2
    assert cb["subject"].startswith("Re: Interview")
    assert result["groups"]["rejected"][0]["messages"] == 2


def test_idempotency_and_dry_run(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/14",
                             status="applied")
    msg = make_msg(frm="talent@acme.com", subject="Interview with Acme Corp",
                   body="Please schedule your interview.", msgid="<id1@acme.com>")
    _run([msg], dry_run=True)
    assert tracker.list_applications()[0]["status"] == "applied"
    assert not inbox.SEEN_PATH.exists()
    r1 = _run([msg])
    assert tracker.list_applications()[0]["status"] == "interview"
    r2 = _run([msg])
    assert r2["skipped_seen"] == 1
    assert len(tracker.list_applications()[0]["callbacks"]) == 1
    assert r1["groups"]["interview"] and not r2["groups"]


def test_cross_account_forward_does_not_duplicate_callback(inbox_env):
    # Addendum B: forwarding preserves Message-ID; second account must not
    # append a second callback for the same message.
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/15",
                             status="applied")
    m = lambda: make_msg(frm="talent@acme.com", subject="Interview with Acme Corp",
                         body="Please schedule your interview.",
                         msgid="<dup1@acme.com>")
    _run([("a@gmail.com", m())])
    _run([("b@asu.edu", m())])
    cbs = tracker.list_applications()[0]["callbacks"]
    assert len(cbs) == 1
    assert "authuser=a%40gmail.com" in cbs[0]["link"]   # first account kept


def test_multi_account_seen_keys_and_tagging(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/16",
                             status="applied")
    m = lambda i: make_msg(frm="talent@acme.com",
                           subject="Interview with Acme Corp",
                           body="Please schedule your interview.",
                           msgid=f"<ma{i}@acme.com>")
    _run([("a@gmail.com", m(1)), ("b@asu.edu", m(2))])
    seen = set(json.loads(inbox.SEEN_PATH.read_text()))
    assert "a@gmail.com|<ma1@acme.com>" in seen
    assert "b@asu.edu|<ma2@acme.com>" in seen
    cbs = tracker.list_applications()[0]["callbacks"]
    assert {c["account"] for c in cbs} == {"a@gmail.com", "b@asu.edu"}


def test_vevent_callback_records_dtstart(inbox_env):
    tracker.save_application(company="Snowflake", role="MLE", url="http://j/17",
                             status="applied")
    msg = make_msg(frm="isabella.childs@snowflake.com",
                   subject="Interview with Snowflake @ Tue Aug 25 12pm",
                   body="", ics=ICS, msgid="<cal1@snowflake.com>")
    _run([msg])
    row = tracker.list_applications()[0]
    assert row["status"] == "interview"
    cb = row["callbacks"][0]
    assert cb["dtstart"] == "2026-08-25T19:00Z"
    assert cb["summary"] == "Interview with Snowflake"


def test_needs_reply_true_and_false(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/18",
                             status="applied")
    msg = make_msg(frm="talent@acme.com", subject="Interview with Acme Corp",
                   body="What is your availability this week?",
                   msgid="<nr1@acme.com>")
    _run([msg], sent_checker=lambda latest, thread: False)   # no reply sent
    assert tracker.list_applications()[0]["callbacks"][0]["needs_reply"] is True

    tracker.save_application(company="Beta Inc", role="SDE", url="http://j/19",
                             status="applied")
    msg2 = make_msg(frm="talent@beta.com", subject="Interview with Beta Inc",
                    body="What is your availability this week?",
                    msgid="<nr2@beta.com>")
    _run([msg2], sent_checker=lambda latest, thread: True)   # already replied
    row2 = next(a for a in tracker.list_applications() if a["url"] == "http://j/19")
    assert row2["callbacks"][0]["needs_reply"] is False


def test_accounts_env_parsing_and_password_hygiene(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_EMAIL", "one@gmail.com")
    monkeypatch.setenv("JOB_AGENT_EMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("JOB_AGENT_EMAIL_2", "two@asu.edu")
    monkeypatch.setenv("JOB_AGENT_EMAIL_APP_PASSWORD_2", "pw2")
    monkeypatch.setenv("JOB_AGENT_IMAP_HOST_2", "imap.other.edu")
    accts = inbox.accounts()
    assert [a["email"] for a in accts] == ["one@gmail.com", "two@asu.edu"]
    assert accts[0]["password"] == "abcdefghijklmnop"   # spaces stripped (D)
    assert accts[0]["host"] == "imap.gmail.com"
    assert accts[1]["host"] == "imap.other.edu"


def test_default_days_from_settings(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "_settings", lambda: {"inbox": {"days": 45}})
    assert inbox.default_days() == 45
    monkeypatch.setattr(config, "_settings", lambda: {})
    assert inbox.default_days() == 14


def test_unconfigured_exits_gracefully(inbox_env, capsys):
    result = inbox.run_inbox()
    assert result == {"ok": False, "reason": "not_configured"}
    out = capsys.readouterr().out
    assert "App Password" in out and "JOB_AGENT_EMAIL_2" in out


def test_html_body_stripped(inbox_env):
    tracker.save_application(company="Acme Corp", role="MLE", url="http://j/20",
                             status="applied")
    result = _run([make_msg(frm="talent@acme.com", subject="Acme Corp next steps",
                            msgid="<ht1@acme.com>",
                            html_body="<html><body><p>Please <b>schedule</b> your "
                                      "interview.</p><style>p{}</style></body></html>")])
    assert result["groups"]["interview"][0]["company"] == "Acme Corp"


# ------------------------------------------------------------------ IMAP safety

class FakeIMAP:
    """Enough of imaplib for fetch_messages: records every command."""

    def __init__(self, raws, fail_mailboxes=()):
        self.raws = raws
        self.fail_mailboxes = fail_mailboxes
        self.selected = []
        self.fetch_specs = []

    def select(self, mailbox, readonly=False):
        self.selected.append((mailbox, readonly))
        if mailbox in self.fail_mailboxes:
            return ("NO", [b""])
        return ("OK", [b"1"])

    def search(self, charset, *criteria):
        ids = " ".join(str(i + 1) for i in range(len(self.raws)))
        return ("OK", [ids.encode()])

    def fetch(self, mids, spec):
        # chunked form: "3,2,1"
        self.fetch_specs.append(spec)
        self.fetch_calls = getattr(self, "fetch_calls", 0) + 1
        out = []
        for mid in str(mids).split(","):
            idx = int(mid) - 1
            out.append((f"{mid} ()".encode(), self.raws[idx]))
            out.append(b")")   # imaplib emits closing frames between tuples
        return ("OK", out)

    def logout(self):
        return ("BYE", [b""])


def _fake_raws(n=3):
    return [make_msg(msgid=f"<f{i}@x.com>").as_bytes() for i in range(n)]


def test_fetch_uses_peek_and_all_mail():
    # Addendum A + H: BODY.PEEK always (never marks mail read), All Mail always.
    fake = FakeIMAP(_fake_raws(3))
    msgs, total = inbox.fetch_messages(14, 10, {"email": "e", "password": "p",
                                                "host": "h"}, conn=fake)
    assert len(msgs) == 3 and total == 3
    assert fake.selected[0] == ('"[Gmail]/All Mail"', True)   # readonly
    assert fake.fetch_specs and all("BODY.PEEK" in s for s in fake.fetch_specs)
    assert all("RFC822" not in s for s in fake.fetch_specs)


def test_fetch_is_chunked_and_connect_uses_timeout(monkeypatch):
    # Robustness: many ids -> few FETCH round-trips; connections carry a socket
    # timeout so a dead connection fails loudly instead of hanging forever.
    fake = FakeIMAP(_fake_raws(250))
    msgs, total = inbox.fetch_messages(14, 250, {"email": "e", "password": "p",
                                                 "host": "h"}, conn=fake)
    assert len(msgs) == 250 and total == 250
    assert fake.fetch_calls <= 3                     # 100 ids per round-trip

    captured = {}

    class FakeSSL:
        def __init__(self, host, timeout=None):
            captured["timeout"] = timeout
            raise OSError("stop here")

    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeSSL)
    with pytest.raises(OSError):
        inbox._connect({"email": "e", "password": "p", "host": "h"})
    assert captured["timeout"] == inbox._IMAP_TIMEOUT


def test_fetch_reports_truncation_and_inbox_fallback():
    fake = FakeIMAP(_fake_raws(5), fail_mailboxes=('"[Gmail]/All Mail"',))
    msgs, total = inbox.fetch_messages(90, 2, {"email": "e", "password": "p",
                                               "host": "h"}, conn=fake)
    assert total == 5 and len(msgs) == 2                      # caller can warn
    assert fake.selected[1][0] == "INBOX"                     # non-Gmail fallback


# ------------------------------------------------------------------ rendering

def _cb(**kw):
    base = {"date": "2026-08-20", "type": "interview", "subject": "Interview",
            "snippet": "s", "msgid": "a@b", "account": "me@x.com",
            "link": "https://mail.google.com/mail/?authuser=x#search/rfc822msgid:a%40b"}
    base.update(kw)
    return base


def test_dashboard_and_focus_escape_untrusted_subjects():
    # Addendum E: subjects/snippets are untrusted; must be escaped everywhere.
    from src.tools import dashboard, focus
    evil = 'Interview <script>alert(1)</script> "quoted"'
    row = {"company": "Acme", "role": "MLE", "url": "http://j/1",
           "status": "interview", "callbacks": [_cb(subject=evil, snippet=evil)]}
    cell = dashboard._callback_cell(row)
    assert "<script>" not in cell and "&lt;script&gt;" in cell
    r = focus._app_row(row, "go", "interview", "p-go", "", False)
    assert "<script>" not in r and "&lt;script&gt;" in r
    lane = focus._callbacks_lane([row])
    assert "<script>" not in lane and "Callbacks" in lane


def test_callbacks_lane_empty_collapses():
    from src.tools import focus
    assert focus._callbacks_lane([]) == ""
    assert focus._callbacks_lane([{"company": "A", "status": "applied"}]) == ""


def test_callbacks_lane_ordering_and_stats():
    from src.tools import focus
    rows = [
        {"company": "Rej Co", "role": "SDE", "url": "u1", "status": "rejected",
         "source": "ashby", "callbacks": [_cb(type="rejected", date="2026-08-19")]},
        {"company": "Iview Co", "role": "MLE", "url": "u2", "status": "interview",
         "source": "ashby",
         "callbacks": [_cb(type="interview", dtstart="2026-08-25T19:00Z",
                           summary="Interview with Iview")]},
        {"company": "Owed Co", "role": "SDE", "url": "u3", "status": "replied",
         "source": "lever",
         "callbacks": [_cb(type="replied", needs_reply=True, date="2026-08-18")]},
        {"company": "Ack Co", "role": "SDE", "url": "u4", "status": "applied",
         "source": "lever", "callbacks": [_cb(type="ack")]},
    ]
    entries = focus._callback_lane_entries(rows)
    order = [e[0]["company"] for e in entries]
    assert order == ["Iview Co", "Owed Co", "Ack Co", "Rej Co"]
    assert entries[-1][6] is True                    # rejection behind the fold
    stats = focus._callback_stats(rows)
    assert stats["rate"] == 75.0                     # ack-only row is not a real callback
    assert stats["interviews"] == 1 and stats["owed"] == 1
    lane = focus._callbacks_lane(rows)
    assert "callback rate 75.0 percent" in lane
    assert "Aug 25, 19:00" in lane                   # agenda time rendered


def test_callback_rate_math_partial():
    from src.tools import focus
    rows = [
        {"company": "A", "status": "applied", "source": "x",
         "callbacks": [_cb()]},
        {"company": "B", "status": "applied", "source": "x"},
        {"company": "C", "status": "applied", "source": "x"},
        {"company": "D", "status": "found", "source": "x"},   # not submitted
    ]
    assert focus._callback_stats(rows)["rate"] == 33.3


def test_dtstart_parsing():
    assert inbox._parse_dtstart("20260825T190000Z") == "2026-08-25T19:00Z"
    assert inbox._parse_dtstart("20260825T1900") == "2026-08-25T19:00"
    assert inbox._parse_dtstart("20260825") == "2026-08-25"
    assert inbox._parse_dtstart("garbage") == ""
