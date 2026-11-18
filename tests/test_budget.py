"""Spec acceptance test 7: 20 gifts across statuses/currencies — totals to the cent."""
import uuid

from app.budget import compute_totals, convert


def g(rid, status, paid=None, est=None, rate=1.0, qty=1, currency="USD", deleted=False):
    return {"id": str(uuid.uuid4()), "recipient_id": rid, "status": status, "price_paid_cents": paid,
            "price_estimate_cents": est, "fx_rate_to_year": rate, "quantity": qty, "currency": currency,
            "deleted_at": "2026-11-01T00:00:00.000Z" if deleted else None}


def test_convert_rounds_half_away_from_zero():
    assert convert(1000, 1.0825) == 1083   # 1082.5 → 1083
    assert convert(999, 0.5) == 500        # 499.5 → 500
    assert convert(1, 0.3333) == 0


def test_twenty_gift_fixture():
    mom, dad, kid, gone = "r-mom", "r-dad", "r-kid", "r-gone"
    recipients = [
        {"id": mom, "name": "Mom", "budget_cents": 20000},
        {"id": dad, "name": "Dad", "budget_cents": 10000},
        {"id": kid, "name": "Kid", "budget_cents": None},
        {"id": gone, "name": "Gone", "budget_cents": 5000, "deleted_at": "2026-11-01T00:00:00.000Z"},
    ]
    gifts = [
        # Mom — spent: 5800 + 12000 + 2599*2=5198 + 4000(est fallback) + EUR 5000*1.0825=5413 = 32411
        g(mom, "ordered", paid=5800, est=6000),
        g(mom, "shipped", paid=12000),
        g(mom, "wrapped", paid=2599, qty=2),
        g(mom, "received", est=4000),                       # purchased, no paid → est
        g(mom, "given", paid=5000, rate=1.0825, currency="EUR"),
        g(mom, "idea", est=3000),                            # projected only
        g(mom, "to_buy", paid=1500),                          # projected fallback to paid
        # Dad — spent: 1999 + GBP 3333*1.27=4232.91→4233 + 0 (no price) = 6232 ; projected +2500*3=7500 +999
        g(dad, "ordered", paid=1999),
        g(dad, "received", paid=3333, rate=1.27, currency="GBP"),
        g(dad, "wrapped"),
        g(dad, "idea", est=2500, qty=3),
        g(dad, "to_buy", est=999),
        # Kid — spent: 899 + 1250 + CAD 4000*0.7333=2933.2→2933 = 5082 ; projected +700 + JPY 300000*0.0067=2010
        g(kid, "shipped", paid=899),
        g(kid, "given", paid=1250),
        g(kid, "ordered", paid=4000, rate=0.7333, currency="CAD"),
        g(kid, "idea", est=700),
        g(kid, "idea", est=300000, rate=0.0067, currency="JPY"),
        g(kid, "to_buy"),
        # Excluded: deleted gift, and gift of deleted recipient
        g(kid, "ordered", paid=99999, deleted=True),
        g(gone, "ordered", paid=88888),
    ]
    assert len(gifts) == 20
    t = compute_totals({"currency": "USD", "total_budget_cents": 50000}, recipients, gifts)

    mom_spent, dad_spent, kid_spent = 32411, 6232, 5082
    mom_proj = mom_spent + 3000 + 1500
    dad_proj = dad_spent + 7500 + 999
    kid_proj = kid_spent + 700 + 2010
    assert t["spent_cents"] == mom_spent + dad_spent + kid_spent == 43725
    assert t["projected_cents"] == mom_proj + dad_proj + kid_proj == 59434
    assert t["remaining_cents"] == 50000 - 43725
    per = {r["name"]: r for r in t["per_recipient"]}
    assert set(per) == {"Mom", "Dad", "Kid"}
    assert (per["Mom"]["spent_cents"], per["Mom"]["projected_cents"]) == (mom_spent, mom_proj)
    assert (per["Dad"]["spent_cents"], per["Dad"]["projected_cents"]) == (dad_spent, dad_proj)
    assert (per["Kid"]["spent_cents"], per["Kid"]["projected_cents"]) == (kid_spent, kid_proj)
    assert per["Mom"]["over_budget"] is True and per["Dad"]["over_budget"] is False and per["Kid"]["over_budget"] is False
    assert t["gifts_by_status"] == {"idea": 4, "to_buy": 3, "ordered": 3, "shipped": 2, "received": 2, "wrapped": 2, "given": 2}
    assert per["Mom"]["gift_count"] == 7 and per["Mom"]["done_count"] == 3
    assert t["people_total"] == 3 and t["people_done"] == 0


def test_people_done_and_no_budget():
    t = compute_totals({"currency": "USD"}, [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                       [g("a", "received", paid=100), g("a", "given", paid=100)])
    assert t["people_done"] == 1 and t["remaining_cents"] is None and t["budget_cents"] is None


def test_totals_endpoint_matches(make_user):
    from tests.conftest import gift_row, recipient_row, year_row
    a = make_user()
    y = year_row(a.user_id, total_budget_cents=10000)
    r = recipient_row(y["id"], budget_cents=5000)
    gifts = [gift_row(y["id"], r["id"], status="ordered", price_paid_cents=2550, quantity=2),
             gift_row(y["id"], r["id"], status="idea", price_estimate_cents=1000, currency="EUR", fx_rate_to_year=1.1)]
    a.sync({"occasion_years": [y], "recipients": [r], "gifts": gifts})
    t = a.get(f"/v1/years/{y['id']}/totals").json()
    assert (t["spent_cents"], t["projected_cents"], t["remaining_cents"]) == (5100, 6200, 4900)
    assert t["per_recipient"][0]["over_budget"] is True
    b = make_user()
    assert b.get(f"/v1/years/{y['id']}/totals").status_code == 403
