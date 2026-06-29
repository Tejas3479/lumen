"""
Lumen Seed Data
Loads a complete judge-ready demo dataset.

Usage:
    cd backend
    python seed_data.py

Idempotent: running twice does not create duplicates.
Requires the database to be running and migrations applied:
    alembic upgrade head
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add backend directory to path so app imports work
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text
from passlib.context import CryptContext

from app.config import settings
from app.models import (
    Category, User, Issue, StatusHistory, Verification,
    Comment, Vote, Badge, UserBadge, LeaderboardPoints,
    PredictiveHotspot,
)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def now() -> datetime:
    return datetime.now(timezone.utc)


def ago(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return now() - timedelta(days=days, hours=hours, minutes=minutes)


# ──────────────────────────────────────────────────────────────
# CATEGORIES
# ──────────────────────────────────────────────────────────────
CATEGORIES = [
    {
        "name": "pothole",
        "display_name": "Pothole / Road Damage",
        "icon": "road",
        "color": "#DC2626",
        "avg_resolution_days": 14.0,
    },
    {
        "name": "garbage",
        "display_name": "Garbage / Waste",
        "icon": "trash-2",
        "color": "#D97706",
        "avg_resolution_days": 5.0,
    },
    {
        "name": "water_leak",
        "display_name": "Water Leak / Supply",
        "icon": "droplets",
        "color": "#2563EB",
        "avg_resolution_days": 10.0,
    },
    {
        "name": "street_light",
        "display_name": "Street Light",
        "icon": "lamp",
        "color": "#7C3AED",
        "avg_resolution_days": 7.0,
    },
    {
        "name": "sewage",
        "display_name": "Sewage / Drainage",
        "icon": "waves",
        "color": "#059669",
        "avg_resolution_days": 12.0,
    },
    {
        "name": "encroachment",
        "display_name": "Encroachment / Obstruction",
        "icon": "alert-triangle",
        "color": "#EA580C",
        "avg_resolution_days": 21.0,
    },
    {
        "name": "graffiti",
        "display_name": "Graffiti / Vandalism",
        "icon": "pen-tool",
        "color": "#DB2777",
        "avg_resolution_days": 8.0,
    },
    {
        "name": "tree",
        "display_name": "Tree / Green Space",
        "icon": "tree-pine",
        "color": "#16A34A",
        "avg_resolution_days": 9.0,
    },
]

# ──────────────────────────────────────────────────────────────
# BADGES
# ──────────────────────────────────────────────────────────────
BADGES = [
    {
        "name": "first_report",
        "display_name": "First Reporter",
        "description": "Filed your very first civic issue report.",
        "icon": "🚀",
        "category": "reporting",
        "points_required": None,
        "condition_json": {"action": "reported", "count": 1},
    },
    {
        "name": "reporter_10",
        "display_name": "Community Watchdog",
        "description": "Reported 10 civic issues.",
        "icon": "🔍",
        "category": "reporting",
        "points_required": None,
        "condition_json": {"action": "reported", "count": 10},
    },
    {
        "name": "reporter_50",
        "display_name": "Guardian of the City",
        "description": "Reported 50 civic issues.",
        "icon": "🏙️",
        "category": "reporting",
        "points_required": None,
        "condition_json": {"action": "reported", "count": 50},
    },
    {
        "name": "verified_5",
        "display_name": "Ground Truth",
        "description": "Verified 5 issues on-site.",
        "icon": "✅",
        "category": "verification",
        "points_required": None,
        "condition_json": {"action": "verified", "count": 5},
    },
    {
        "name": "streak_7",
        "display_name": "Week Warrior",
        "description": "7-day reporting streak.",
        "icon": "🔥",
        "category": "streak",
        "points_required": None,
        "condition_json": {"streak_days": 7},
    },
    {
        "name": "streak_30",
        "display_name": "Month Champion",
        "description": "30-day reporting streak.",
        "icon": "🏆",
        "category": "streak",
        "points_required": None,
        "condition_json": {"streak_days": 30},
    },
    {
        "name": "impact_100",
        "display_name": "Century Club",
        "description": "Earned 100 points through civic action.",
        "icon": "💯",
        "category": "impact",
        "points_required": 100,
        "condition_json": {"points": 100},
    },
    {
        "name": "impact_500",
        "display_name": "City Changer",
        "description": "Earned 500 points.",
        "icon": "⚡",
        "category": "impact",
        "points_required": 500,
        "condition_json": {"points": 500},
    },
    {
        "name": "emergency_reporter",
        "display_name": "Emergency Responder",
        "description": "Reported a critical emergency issue.",
        "icon": "🚨",
        "category": "special",
        "points_required": None,
        "condition_json": {"action": "reported_emergency", "count": 1},
    },
    {
        "name": "resolution_confirmed",
        "display_name": "Resolution Hero",
        "description": "Confirmed an issue was resolved.",
        "icon": "🎯",
        "category": "impact",
        "points_required": None,
        "condition_json": {"action": "resolved_confirmed", "count": 1},
    },
    {
        "name": "first_responder",
        "display_name": "First Responder",
        "description": "First to verify a newly reported issue.",
        "icon": "⚡",
        "category": "special",
        "points_required": None,
        "condition_json": {"action": "first_verifier"},
    },
]

# ──────────────────────────────────────────────────────────────
# ISSUES — 28 issues covering all 6 categories and 4 statuses
# Centred around Mumbai's Andheri/Bandra corridor for a realistic
# map cluster. Two hotspot clusters:
#   Cluster A — Andheri West (potholes)  ~19.136, 72.833
#   Cluster B — Bandra East (water/sewer)~19.054, 72.855
# ──────────────────────────────────────────────────────────────
def build_issues(cats: dict, users: dict) -> list[dict]:
    reporter = users["reporter"]
    reporter2 = users["reporter2"]
    official = users["official"]
    admin = users["admin"]

    return [
        # ──── CLUSTER A: Andheri West — Potholes (5 issues) ────
        {
            "title": "Giant pothole on SV Road near Lokhandwala",
            "description": (
                "A massive 2-foot deep pothole has appeared at the junction of SV Road "
                "and Lokhandwala Circle. Two scooters already had punctures this morning. "
                "The crater is getting bigger with each rain."
            ),
            "category": "pothole",
            "severity": "critical",
            "status": "in_progress",
            "latitude": 19.1370,
            "longitude": 72.8322,
            "address": "SV Road, Lokhandwala Circle, Andheri West",
            "ward": "K/West",
            "zone": "Western Suburbs",
            "reporter": reporter,
            "vote_count": 47,
            "verification_count": 8,
            "view_count": 234,
            "is_emergency": False,
            "ai_category": "pothole",
            "ai_severity": "critical",
            "ai_confidence": 0.97,
            "ai_explanation": "Image analysis confirms road surface failure exceeding 30cm depth. High traffic zone.",
            "ai_summary": "Critical pothole at major intersection, immediate repair required.",
            "created_at": ago(days=12),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 12, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 11, "by": reporter2, "note": "Verified on site — extremely dangerous"},
                {"from_s": "verified", "to_s": "assigned", "days_ago": 9, "by": official, "note": "Assigned to Roads dept"},
                {"from_s": "assigned", "to_s": "in_progress", "days_ago": 6, "by": official, "note": "Repair crew dispatched"},
            ],
        },
        {
            "title": "Series of potholes on Andheri Link Road",
            "description": (
                "At least 6 potholes in a 200m stretch of Andheri Link Road between "
                "the flyover and D-Mart. Auto-rickshaws are swerving dangerously. "
                "The road was dug up for cable laying 3 months ago and never properly repaired."
            ),
            "category": "pothole",
            "severity": "high",
            "status": "verified",
            "latitude": 19.1358,
            "longitude": 72.8298,
            "address": "Andheri Link Road, near D-Mart, Andheri West",
            "ward": "K/West",
            "zone": "Western Suburbs",
            "reporter": reporter2,
            "vote_count": 31,
            "verification_count": 5,
            "view_count": 156,
            "is_emergency": False,
            "ai_category": "pothole",
            "ai_severity": "high",
            "ai_confidence": 0.94,
            "ai_explanation": "Multiple surface failures detected from photo. Utility trench restoration failure pattern.",
            "ai_summary": "Multiple potholes from poor post-dig restoration over 200m stretch.",
            "created_at": ago(days=8),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 8, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 7, "by": reporter, "note": "Confirmed — counted 7 potholes"},
            ],
        },
        {
            "title": "Road cave-in near Versova bus depot",
            "description": (
                "The road has partially caved in outside Versova bus depot. Depth is about 1.5 feet. "
                "Buses are driving around it but it's blocking half the lane. "
                "Fear of gas pipe rupture underneath."
            ),
            "category": "pothole",
            "severity": "critical",
            "status": "reported",
            "latitude": 19.1389,
            "longitude": 72.8276,
            "address": "Near Versova Bus Depot, Andheri West",
            "ward": "K/West",
            "zone": "Western Suburbs",
            "reporter": reporter,
            "vote_count": 19,
            "verification_count": 2,
            "view_count": 89,
            "is_emergency": True,
            "ai_category": "pothole",
            "ai_severity": "critical",
            "ai_confidence": 0.98,
            "ai_explanation": "Subsidence pattern detected. Risk of utility pipe rupture. Emergency classification recommended.",
            "ai_summary": "Road cave-in with utility rupture risk — emergency response needed.",
            "created_at": ago(hours=4),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 0, "hours_ago": 4, "by": reporter, "note": "URGENT: Road cave-in, buses barely passing"},
            ],
        },
        {
            "title": "Pothole filled but deteriorating again — SV Road",
            "description": (
                "The pothole at SV Road near Om Nagar was filled 3 weeks ago but is already "
                "breaking down again. The repair was superficial. Same issue every monsoon season."
            ),
            "category": "pothole",
            "severity": "medium",
            "status": "resolved",
            "latitude": 19.1341,
            "longitude": 72.8311,
            "address": "SV Road near Om Nagar, Andheri West",
            "ward": "K/West",
            "zone": "Western Suburbs",
            "reporter": reporter2,
            "vote_count": 12,
            "verification_count": 3,
            "view_count": 67,
            "is_emergency": False,
            "ai_category": "pothole",
            "ai_severity": "medium",
            "ai_confidence": 0.88,
            "ai_explanation": "Recurring pothole pattern at same location suggests drainage failure.",
            "ai_summary": "Recurring pothole — previously filled but quality of repair poor.",
            "created_at": ago(days=28),
            "resolved_at": ago(days=7),
            "resolution_notes": "Road repair completed. Proper sub-base laid this time.",
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 28, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 27, "by": reporter, "note": "Confirmed recurrence"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 20, "by": official, "note": "Proper repair scheduled"},
                {"from_s": "in_progress", "to_s": "resolved", "days_ago": 7, "by": official, "note": "Repair completed with proper sub-base"},
            ],
        },
        {
            "title": "Pothole at school crossing — child safety risk",
            "description": (
                "There is a deep pothole right at the pedestrian crossing outside St. Mary's School. "
                "Children jump over it every morning. A parent almost fell while carrying a toddler. "
                "This is a safety emergency during school hours."
            ),
            "category": "pothole",
            "severity": "high",
            "status": "reported",
            "latitude": 19.1352,
            "longitude": 72.8341,
            "address": "Outside St. Mary's School, Andheri West",
            "ward": "K/West",
            "zone": "Western Suburbs",
            "reporter": reporter,
            "vote_count": 28,
            "verification_count": 6,
            "view_count": 112,
            "is_emergency": False,
            "ai_category": "pothole",
            "ai_severity": "high",
            "ai_confidence": 0.91,
            "ai_explanation": "Pedestrian crossing with school proximity. High injury risk for children.",
            "ai_summary": "Hazardous pothole at school crossing, heightened child safety risk.",
            "created_at": ago(days=3),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 3, "by": reporter, "note": "School safety risk — please prioritize"},
            ],
        },

        # ──── CLUSTER B: Bandra East — Water & Sewage (5 issues) ────
        {
            "title": "Burst water main flooding BKC road",
            "description": (
                "A water main has burst on the approach road to BKC Gate 4. "
                "Water is shooting up 2 feet and the road is completely flooded. "
                "Traffic is at a standstill. Multiple vehicles stuck."
            ),
            "category": "water_leak",
            "severity": "critical",
            "status": "in_progress",
            "latitude": 19.0544,
            "longitude": 72.8656,
            "address": "BKC Road, Gate 4 approach, Bandra East",
            "ward": "H/East",
            "zone": "Eastern Suburbs",
            "reporter": reporter2,
            "vote_count": 89,
            "verification_count": 14,
            "view_count": 567,
            "is_emergency": True,
            "ai_category": "water_leak",
            "ai_severity": "critical",
            "ai_confidence": 0.99,
            "ai_explanation": "Burst main confirmed by visual. Road flooding active. Emergency classification assigned.",
            "ai_summary": "Burst water main causing major road flooding at BKC, emergency response active.",
            "created_at": ago(hours=6),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 0, "hours_ago": 6, "by": reporter2, "note": "EMERGENCY: Road completely flooded"},
                {"from_s": "reported", "to_s": "verified", "days_ago": 0, "hours_ago": 5, "by": reporter, "note": "Confirmed burst main"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 0, "hours_ago": 4, "by": official, "note": "Repair crew dispatched, traffic diverted"},
            ],
        },
        {
            "title": "Sewage overflow near Kurla market",
            "description": (
                "The sewage manhole near Kurla market has been overflowing for 3 days. "
                "The smell is unbearable and children are playing nearby. "
                "Black water is running into the vegetable market area."
            ),
            "category": "sewage",
            "severity": "high",
            "status": "assigned",
            "latitude": 19.0726,
            "longitude": 72.8795,
            "address": "Near Kurla Market, LBS Road, Kurla",
            "ward": "L",
            "zone": "Eastern Suburbs",
            "reporter": reporter,
            "vote_count": 56,
            "verification_count": 9,
            "view_count": 289,
            "is_emergency": False,
            "ai_category": "sewage",
            "ai_severity": "high",
            "ai_confidence": 0.95,
            "ai_explanation": "Sewage overflow into food market area. Public health risk. High priority.",
            "ai_summary": "Sewage overflow contaminating market area — public health emergency.",
            "created_at": ago(days=5),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 5, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 4, "by": reporter2, "note": "Confirmed overflow"},
                {"from_s": "verified", "to_s": "assigned", "days_ago": 2, "by": official, "note": "Assigned to Hydraulics dept"},
            ],
        },
        {
            "title": "Waterlogging on Dharavi road during rains",
            "description": (
                "Every time it rains, Dharavi Road between the two bridges becomes completely "
                "waterlogged knee-deep. The storm drain is permanently blocked. "
                "Residents have complained for 3 years."
            ),
            "category": "sewage",
            "severity": "high",
            "status": "resolved",
            "latitude": 19.0416,
            "longitude": 72.8549,
            "address": "Dharavi Road between bridges, Dharavi",
            "ward": "F/North",
            "zone": "Central",
            "reporter": reporter2,
            "vote_count": 103,
            "verification_count": 22,
            "view_count": 1240,
            "is_emergency": False,
            "ai_category": "sewage",
            "ai_severity": "high",
            "ai_confidence": 0.96,
            "ai_explanation": "Chronic drainage failure at this location. Historical data confirms recurrence.",
            "ai_summary": "Chronic waterlogging from blocked storm drain — longstanding community issue.",
            "created_at": ago(days=45),
            "resolved_at": ago(days=10),
            "resolution_notes": "Storm drain desilted and expanded. New grating installed.",
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 45, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 44, "by": reporter, "note": "Third year in a row"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 30, "by": official, "note": "Desilting work started"},
                {"from_s": "in_progress", "to_s": "resolved", "days_ago": 10, "by": official, "note": "Drain expanded and new grating installed"},
            ],
        },
        {
            "title": "No water supply for 48 hours in Bandra West",
            "description": (
                "No water supply in Hill Road area since yesterday 6am. "
                "About 500 households affected. The MCGM helpline is unreachable. "
                "Elderly residents and young children severely impacted."
            ),
            "category": "water_leak",
            "severity": "high",
            "status": "verified",
            "latitude": 19.0568,
            "longitude": 72.8374,
            "address": "Hill Road, Bandra West",
            "ward": "H/West",
            "zone": "Western Suburbs",
            "reporter": reporter,
            "vote_count": 74,
            "verification_count": 11,
            "view_count": 432,
            "is_emergency": False,
            "ai_category": "water_leak",
            "ai_severity": "high",
            "ai_confidence": 0.93,
            "ai_explanation": "Multiple reporters confirm same issue from same area. Supply disruption confirmed.",
            "ai_summary": "500 households without water for 48h in Bandra West.",
            "created_at": ago(days=2),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 2, "by": reporter, "note": "500 families without water"},
                {"from_s": "reported", "to_s": "verified", "days_ago": 1, "by": reporter2, "note": "Confirmed — our building also dry"},
            ],
        },
        {
            "title": "Manhole cover missing on busy road",
            "description": (
                "Manhole cover near Carter Road roundabout has been missing for 6 days. "
                "The open manhole is 3 feet deep. A cyclist nearly fell in last night. "
                "Someone put a plastic crate over it but it's not safe."
            ),
            "category": "sewage",
            "severity": "critical",
            "status": "in_progress",
            "latitude": 19.0656,
            "longitude": 72.8243,
            "address": "Carter Road Roundabout, Bandra West",
            "ward": "H/West",
            "zone": "Western Suburbs",
            "reporter": reporter2,
            "vote_count": 61,
            "verification_count": 7,
            "view_count": 378,
            "is_emergency": True,
            "ai_category": "sewage",
            "ai_severity": "critical",
            "ai_confidence": 0.98,
            "ai_explanation": "Open manhole on high-traffic road. Immediate safety risk. Emergency.",
            "ai_summary": "Missing manhole cover near Carter Road — fall hazard, emergency.",
            "created_at": ago(days=6),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 6, "by": reporter2, "note": "DANGER: Open manhole with no cover"},
                {"from_s": "reported", "to_s": "verified", "days_ago": 5, "by": reporter, "note": "Confirmed — just put traffic cone"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 3, "by": official, "note": "New cover ordered"},
            ],
        },

        # ──── GARBAGE (5 issues) ────
        {
            "title": "Illegal garbage dump behind Chembur station",
            "description": (
                "A massive illegal garbage dump has formed behind Chembur railway station. "
                "It now spans about 30 meters. Rag pickers are sorting through it "
                "and children play nearby. The stench reaches three streets away."
            ),
            "category": "garbage",
            "severity": "high",
            "status": "reported",
            "latitude": 19.0623,
            "longitude": 72.8995,
            "address": "Behind Chembur Railway Station, Chembur",
            "ward": "M/East",
            "zone": "Eastern Suburbs",
            "reporter": reporter,
            "vote_count": 38,
            "verification_count": 4,
            "view_count": 178,
            "is_emergency": False,
            "ai_category": "garbage",
            "ai_severity": "high",
            "ai_confidence": 0.92,
            "ai_explanation": "Large-scale illegal dumping detected. Health hazard confirmed.",
            "ai_summary": "30m illegal dump near station — public health risk.",
            "created_at": ago(days=4),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 4, "by": reporter, "note": None},
            ],
        },
        {
            "title": "Garbage truck not collecting from Ghatkopar East",
            "description": (
                "The garbage truck has not come to Sahakar Nagar, Ghatkopar East for 9 days. "
                "All residents have put out bins but they remain uncollected. "
                "Bins are overflowing and stray dogs have spread garbage across the lane."
            ),
            "category": "garbage",
            "severity": "medium",
            "status": "resolved",
            "latitude": 19.0778,
            "longitude": 72.9087,
            "address": "Sahakar Nagar, Ghatkopar East",
            "ward": "N",
            "zone": "Eastern Suburbs",
            "reporter": reporter2,
            "vote_count": 45,
            "verification_count": 8,
            "view_count": 221,
            "is_emergency": False,
            "ai_category": "garbage",
            "ai_severity": "medium",
            "ai_confidence": 0.89,
            "ai_explanation": "Garbage collection disruption. Multiple household complaint pattern.",
            "ai_summary": "9-day garbage collection failure in residential colony.",
            "created_at": ago(days=15),
            "resolved_at": ago(days=5),
            "resolution_notes": "Collection route resumed. Driver changed. Daily collection confirmed.",
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 15, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 14, "by": reporter, "note": "Same in our lane too"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 10, "by": official, "note": "Route supervisor contacted"},
                {"from_s": "in_progress", "to_s": "resolved", "days_ago": 5, "by": official, "note": "Collection normalized"},
            ],
        },
        {
            "title": "Construction waste dumped on Dadar footpath",
            "description": (
                "A construction contractor has dumped rubble and debris on the footpath "
                "outside the new building on NC Kelkar Road, Dadar. "
                "Pedestrians including wheelchair users cannot pass. "
                "It's been there 11 days."
            ),
            "category": "encroachment",
            "severity": "medium",
            "status": "verified",
            "latitude": 19.0183,
            "longitude": 72.8469,
            "address": "NC Kelkar Road, Dadar West",
            "ward": "G/North",
            "zone": "Central",
            "reporter": reporter,
            "vote_count": 27,
            "verification_count": 4,
            "view_count": 134,
            "is_emergency": False,
            "ai_category": "encroachment",
            "ai_severity": "medium",
            "ai_confidence": 0.87,
            "ai_explanation": "Construction debris blocking pedestrian right of way.",
            "ai_summary": "Construction rubble blocking footpath for 11 days.",
            "created_at": ago(days=11),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 11, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 10, "by": reporter2, "note": "Confirmed — wheelchair users affected"},
            ],
        },
        {
            "title": "Garbage burning near Govandi slum",
            "description": (
                "Residents are burning garbage in the open near Transit Camp, Govandi. "
                "This happens every evening at 6pm. The smoke is causing respiratory issues. "
                "Many children in the area have asthma."
            ),
            "category": "garbage",
            "severity": "high",
            "status": "reported",
            "latitude": 19.0389,
            "longitude": 72.9241,
            "address": "Near Transit Camp, Govandi East",
            "ward": "M/West",
            "zone": "Eastern Suburbs",
            "reporter": reporter2,
            "vote_count": 33,
            "verification_count": 5,
            "view_count": 167,
            "is_emergency": False,
            "ai_category": "garbage",
            "ai_severity": "high",
            "ai_confidence": 0.90,
            "ai_explanation": "Open burning near residential area with children. Air quality hazard.",
            "ai_summary": "Daily garbage burning causing health issues in area with child asthma cases.",
            "created_at": ago(days=7),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 7, "by": reporter2, "note": "Daily occurrence at 6pm"},
            ],
        },
        {
            "title": "Beach garbage after weekend at Juhu",
            "description": (
                "Juhu Beach is covered in weekend garbage — plastic bottles, food containers, "
                "and festival remnants. The MCGM cleaning crew never shows up on Monday mornings. "
                "Volunteers cleaned last time but it's the corporation's job."
            ),
            "category": "garbage",
            "severity": "medium",
            "status": "resolved",
            "latitude": 19.1003,
            "longitude": 72.8265,
            "address": "Juhu Beach, Juhu",
            "ward": "K/West",
            "zone": "Western Suburbs",
            "reporter": reporter,
            "vote_count": 71,
            "verification_count": 15,
            "view_count": 892,
            "is_emergency": False,
            "ai_category": "garbage",
            "ai_severity": "medium",
            "ai_confidence": 0.86,
            "ai_explanation": "Recurring beach littering pattern. Post-weekend spike confirmed by historical data.",
            "ai_summary": "Post-weekend beach garbage at Juhu — MCGM cleanup needed.",
            "created_at": ago(days=9),
            "resolved_at": ago(days=8),
            "resolution_notes": "Emergency cleanup conducted Monday 6am. 4 trucks deployed.",
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 9, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 9, "by": reporter2, "note": "Confirmed 200m stretch covered"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 9, "by": official, "note": "Cleanup crew dispatched"},
                {"from_s": "in_progress", "to_s": "resolved", "days_ago": 8, "by": official, "note": "Beach cleaned — 4 trucks, 12 workers"},
            ],
        },

        # ──── STREET LIGHTS (4 issues) ────
        {
            "title": "Entire street dark — 8 lights out on MG Road",
            "description": (
                "All 8 streetlights on a 400m stretch of MG Road between Vile Parle "
                "station and the flyover are not working. Been dark for 5 nights. "
                "Chain snatching incident already reported in this area last night."
            ),
            "category": "street_light",
            "severity": "high",
            "status": "in_progress",
            "latitude": 19.0990,
            "longitude": 72.8491,
            "address": "MG Road, between Vile Parle Station and flyover",
            "ward": "K/East",
            "zone": "Western Suburbs",
            "reporter": reporter2,
            "vote_count": 52,
            "verification_count": 9,
            "view_count": 312,
            "is_emergency": False,
            "ai_category": "street_light",
            "ai_severity": "high",
            "ai_confidence": 0.93,
            "ai_explanation": "Multiple streetlight failure in high-crime risk zone. Safety concern elevated.",
            "ai_summary": "8 streetlights out on 400m stretch, crime risk elevated.",
            "created_at": ago(days=5),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 5, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 4, "by": reporter, "note": "Confirmed all 8 out"},
                {"from_s": "verified", "to_s": "assigned", "days_ago": 3, "by": official, "note": "Assigned to Electrical dept"},
                {"from_s": "assigned", "to_s": "in_progress", "days_ago": 1, "by": official, "note": "Electricians on site"},
            ],
        },
        {
            "title": "Flickering streetlight causing epilepsy risk",
            "description": (
                "The streetlight outside Mulund Police Chowky has been flickering "
                "at high frequency for 2 weeks. Residents with epilepsy cannot use this road. "
                "The police station itself said they reported it but nothing happened."
            ),
            "category": "street_light",
            "severity": "medium",
            "status": "reported",
            "latitude": 19.1731,
            "longitude": 72.9561,
            "address": "Outside Mulund Police Chowky, Mulund West",
            "ward": "T",
            "zone": "Eastern Suburbs",
            "reporter": reporter,
            "vote_count": 18,
            "verification_count": 3,
            "view_count": 78,
            "is_emergency": False,
            "ai_category": "street_light",
            "ai_severity": "medium",
            "ai_confidence": 0.85,
            "ai_explanation": "Flickering light with health risk noted. Standard priority repair.",
            "ai_summary": "High-frequency flickering streetlight with epilepsy risk for residents.",
            "created_at": ago(days=14),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 14, "by": reporter, "note": "Epilepsy patients cannot use this road"},
            ],
        },
        {
            "title": "Streetlight pole leaning dangerously",
            "description": (
                "A streetlight pole on Linking Road near Shoppers Stop is leaning "
                "at about 45 degrees. It looks like it may fall. "
                "The base concrete is visibly cracked. Wind could topple it."
            ),
            "category": "street_light",
            "severity": "critical",
            "status": "verified",
            "latitude": 19.0611,
            "longitude": 72.8352,
            "address": "Linking Road near Shoppers Stop, Bandra West",
            "ward": "H/West",
            "zone": "Western Suburbs",
            "reporter": reporter2,
            "vote_count": 44,
            "verification_count": 7,
            "view_count": 256,
            "is_emergency": True,
            "ai_category": "street_light",
            "ai_severity": "critical",
            "ai_confidence": 0.97,
            "ai_explanation": "Structural failure of utility pole. Imminent collapse risk. Emergency.",
            "ai_summary": "Streetlight pole leaning at 45° with cracked base — collapse risk.",
            "created_at": ago(days=2),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 2, "by": reporter2, "note": "DANGER: pole may fall"},
                {"from_s": "reported", "to_s": "verified", "days_ago": 1, "by": reporter, "note": "Confirmed — base cracked visibly"},
            ],
        },
        {
            "title": "All lights out in Dharavi lane after cable theft",
            "description": (
                "The underground power cable for the streetlights in Rajiv Nagar, Dharavi "
                "was stolen 4 nights ago. The entire lane (300m) has been dark since. "
                "Women and girls cannot travel safely after 7pm."
            ),
            "category": "street_light",
            "severity": "high",
            "status": "assigned",
            "latitude": 19.0435,
            "longitude": 72.8513,
            "address": "Rajiv Nagar Lane, Dharavi",
            "ward": "F/North",
            "zone": "Central",
            "reporter": reporter,
            "vote_count": 63,
            "verification_count": 11,
            "view_count": 445,
            "is_emergency": False,
            "ai_category": "street_light",
            "ai_severity": "high",
            "ai_confidence": 0.92,
            "ai_explanation": "Cable theft leaving 300m area dark. Safety risk for women.",
            "ai_summary": "300m lane dark after cable theft — women's safety risk.",
            "created_at": ago(days=4),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 4, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 3, "by": reporter2, "note": "Confirmed cable missing"},
                {"from_s": "verified", "to_s": "assigned", "days_ago": 2, "by": official, "note": "Assigned to BEST electrical"},
            ],
        },

        # ──── ENCROACHMENT (3 issues) ────
        {
            "title": "Hawker blocking entire footpath at Kurla junction",
            "description": (
                "A permanent vada pav stall has been illegally set up blocking "
                "the entire footpath at Kurla junction. Pedestrians walk on the road. "
                "Two near-misses with buses this week."
            ),
            "category": "encroachment",
            "severity": "high",
            "status": "reported",
            "latitude": 19.0728,
            "longitude": 72.8800,
            "address": "Kurla Junction Footpath, LBS Road",
            "ward": "L",
            "zone": "Eastern Suburbs",
            "reporter": reporter2,
            "vote_count": 29,
            "verification_count": 4,
            "view_count": 143,
            "is_emergency": False,
            "ai_category": "encroachment",
            "ai_severity": "high",
            "ai_confidence": 0.88,
            "ai_explanation": "Permanent structure blocking pedestrian path on arterial road. Road safety risk.",
            "ai_summary": "Illegal hawker stall blocks entire footpath at busy junction.",
            "created_at": ago(days=6),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 6, "by": reporter2, "note": None},
            ],
        },
        {
            "title": "Parked trucks blocking school bus access",
            "description": (
                "Three large trucks are permanently parked on the side road "
                "leading to New English School, Matunga. School buses cannot turn. "
                "Parents are dropping children on the main road which is dangerous."
            ),
            "category": "encroachment",
            "severity": "high",
            "status": "verified",
            "latitude": 19.0278,
            "longitude": 72.8589,
            "address": "Lane to New English School, Matunga",
            "ward": "F/South",
            "zone": "Central",
            "reporter": reporter,
            "vote_count": 41,
            "verification_count": 6,
            "view_count": 198,
            "is_emergency": False,
            "ai_category": "encroachment",
            "ai_severity": "high",
            "ai_confidence": 0.90,
            "ai_explanation": "Vehicle obstruction blocking school access. Child safety risk.",
            "ai_summary": "Trucks blocking school bus route — children dropped on dangerous main road.",
            "created_at": ago(days=10),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 10, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 9, "by": reporter2, "note": "3 trucks confirmed — been here 2 weeks"},
            ],
        },
        {
            "title": "Illegal food stalls blocking fire exit",
            "description": (
                "Three illegal food stalls have set up in front of the fire exit "
                "of Huma Mall, Kanjurmarg. The exit is completely blocked. "
                "In case of emergency, this exit cannot be used."
            ),
            "category": "encroachment",
            "severity": "critical",
            "status": "reported",
            "latitude": 19.1219,
            "longitude": 72.9347,
            "address": "Outside Huma Mall Fire Exit, Kanjurmarg West",
            "ward": "S",
            "zone": "Eastern Suburbs",
            "reporter": reporter2,
            "vote_count": 35,
            "verification_count": 5,
            "view_count": 167,
            "is_emergency": True,
            "ai_category": "encroachment",
            "ai_severity": "critical",
            "ai_confidence": 0.95,
            "ai_explanation": "Fire exit obstruction. Life safety risk. Emergency classification.",
            "ai_summary": "Fire exit blocked by stalls at mall — life safety emergency.",
            "created_at": ago(days=1),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 1, "by": reporter2, "note": "FIRE SAFETY: exit completely blocked"},
            ],
        },

        # ──── TREE (3 issues) ────
        {
            "title": "Fallen tree blocking road after storm",
            "description": (
                "A large gulmohar tree fell across Peddar Road last night during the storm. "
                "It is blocking both lanes. Traffic completely diverted. "
                "Some cars trapped on the other side."
            ),
            "category": "tree",
            "severity": "critical",
            "status": "resolved",
            "latitude": 18.9712,
            "longitude": 72.8063,
            "address": "Peddar Road, near Kemp's Corner, Mumbai South",
            "ward": "G/South",
            "zone": "South Mumbai",
            "reporter": reporter,
            "vote_count": 82,
            "verification_count": 18,
            "view_count": 1678,
            "is_emergency": True,
            "ai_category": "tree",
            "ai_severity": "critical",
            "ai_confidence": 0.99,
            "ai_explanation": "Major road obstruction confirmed. Emergency tree removal needed.",
            "ai_summary": "Fallen tree blocking Peddar Road — emergency clearance needed.",
            "created_at": ago(days=3),
            "resolved_at": ago(days=2, hours=16),
            "resolution_notes": "Tree removed by MCGM tree gang in 6 hours. Road cleared.",
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 3, "by": reporter, "note": "EMERGENCY: road completely blocked"},
                {"from_s": "reported", "to_s": "verified", "days_ago": 3, "by": reporter2, "note": "Confirmed — both lanes blocked"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 2, "hours_ago": 22, "by": official, "note": "Tree gang dispatched"},
                {"from_s": "in_progress", "to_s": "resolved", "days_ago": 2, "hours_ago": 16, "by": official, "note": "Tree removed, road clear"},
            ],
        },
        {
            "title": "Dead tree leaning over school compound wall",
            "description": (
                "A large dead tree on Worli Sea Face Road is leaning against the compound wall "
                "of St. Xavier's school. Strong winds could bring it down on the school premises. "
                "The tree has visible rot and no leaves for 3 months."
            ),
            "category": "tree",
            "severity": "high",
            "status": "reported",
            "latitude": 18.9967,
            "longitude": 72.8143,
            "address": "Worli Sea Face Road near St. Xavier's School",
            "ward": "G/South",
            "zone": "South Mumbai",
            "reporter": reporter2,
            "vote_count": 23,
            "verification_count": 3,
            "view_count": 112,
            "is_emergency": False,
            "ai_category": "tree",
            "ai_severity": "high",
            "ai_confidence": 0.91,
            "ai_explanation": "Dead tree structural risk near school. Arborist assessment needed.",
            "ai_summary": "Dead rotting tree leaning on school wall — wind-fall risk.",
            "created_at": ago(days=8),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 8, "by": reporter2, "note": None},
            ],
        },
        {
            "title": "Tree roots destroying footpath and water pipe",
            "description": (
                "Massive banyan tree roots have lifted and destroyed a 15m section of footpath "
                "on Altamount Road. The roots have also cracked the water pipe below — "
                "you can see water seeping through. Both problems need coordinated fixing."
            ),
            "category": "tree",
            "severity": "medium",
            "status": "in_progress",
            "latitude": 18.9776,
            "longitude": 72.8098,
            "address": "Altamount Road near Napeansea Road junction",
            "ward": "G/South",
            "zone": "South Mumbai",
            "reporter": reporter,
            "vote_count": 17,
            "verification_count": 4,
            "view_count": 89,
            "is_emergency": False,
            "ai_category": "tree",
            "ai_severity": "medium",
            "ai_confidence": 0.83,
            "ai_explanation": "Tree root infrastructure damage to footpath and water pipe. Dual dept coordination required.",
            "ai_summary": "Banyan roots damaging footpath and causing water pipe leakage.",
            "created_at": ago(days=20),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 20, "by": reporter, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 19, "by": reporter2, "note": "Confirmed pipe leak visible"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 14, "by": official, "note": "Tree dept + hydraulics coordinating"},
            ],
        },

        # ──── GRAFFITI (3 issues) ────
        {
            "title": "Obscene graffiti on school compound wall",
            "description": (
                "Highly obscene graffiti has been spray painted on the compound wall of "
                "Shivaji Park Municipal School over the weekend. Children see it every morning. "
                "Parents are angry. Please clean as soon as possible."
            ),
            "category": "graffiti",
            "severity": "high",
            "status": "resolved",
            "latitude": 19.0234,
            "longitude": 72.8423,
            "address": "Shivaji Park Municipal School wall, Dadar West",
            "ward": "G/North",
            "zone": "Central",
            "reporter": reporter2,
            "vote_count": 55,
            "verification_count": 8,
            "view_count": 334,
            "is_emergency": False,
            "ai_category": "graffiti",
            "ai_severity": "high",
            "ai_confidence": 0.96,
            "ai_explanation": "Obscene content on school property. High priority removal.",
            "ai_summary": "Obscene graffiti on school wall — children exposed daily.",
            "created_at": ago(days=7),
            "resolved_at": ago(days=5),
            "resolution_notes": "Wall painted over in 48 hours. CCTV footage being reviewed.",
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 7, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 6, "by": reporter, "note": "Confirmed extremely inappropriate"},
                {"from_s": "verified", "to_s": "in_progress", "days_ago": 6, "by": official, "note": "Cleaning team assigned"},
                {"from_s": "in_progress", "to_s": "resolved", "days_ago": 5, "by": official, "note": "Wall repainted"},
            ],
        },
        {
            "title": "Gang tags on heritage building facade",
            "description": (
                "Gang-related tags have appeared on the facade of the 100-year-old "
                "Portuguese-era building at Mahim. This is a heritage structure. "
                "The graffiti is causing irreversible damage to lime plaster."
            ),
            "category": "graffiti",
            "severity": "medium",
            "status": "reported",
            "latitude": 19.0434,
            "longitude": 72.8421,
            "address": "Heritage Building on Father Agnel Road, Mahim",
            "ward": "G/North",
            "zone": "Central",
            "reporter": reporter,
            "vote_count": 21,
            "verification_count": 3,
            "view_count": 98,
            "is_emergency": False,
            "ai_category": "graffiti",
            "ai_severity": "medium",
            "ai_confidence": 0.84,
            "ai_explanation": "Heritage structure damage. Requires specialist restoration approach.",
            "ai_summary": "Graffiti on heritage building lime plaster — requires specialist removal.",
            "created_at": ago(days=5),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 5, "by": reporter, "note": "Heritage damage — needs specialist"},
            ],
        },
        {
            "title": "Political graffiti covering entire bus shelter",
            "description": (
                "An entire BEST bus shelter on Western Express Highway near Andheri has been "
                "covered in political party graffiti. Cannot see the bus route numbers. "
                "This is a pre-election violation of model code of conduct."
            ),
            "category": "graffiti",
            "severity": "low",
            "status": "verified",
            "latitude": 19.1156,
            "longitude": 72.8701,
            "address": "WEH Bus Stop near Andheri Station, Andheri East",
            "ward": "K/East",
            "zone": "Western Suburbs",
            "reporter": reporter2,
            "vote_count": 14,
            "verification_count": 2,
            "view_count": 67,
            "is_emergency": False,
            "ai_category": "graffiti",
            "ai_severity": "low",
            "ai_confidence": 0.79,
            "ai_explanation": "Public infrastructure defacement. Low urgency but code of conduct violation.",
            "ai_summary": "Political graffiti on bus shelter obstructing route info.",
            "created_at": ago(days=3),
            "status_transitions": [
                {"from_s": None, "to_s": "reported", "days_ago": 3, "by": reporter2, "note": None},
                {"from_s": "reported", "to_s": "verified", "days_ago": 2, "by": reporter, "note": "Confirmed — 3 party logos painted"},
            ],
        },
    ]


# ──────────────────────────────────────────────────────────────
# HOTSPOTS (pre-computed for demo)
# ──────────────────────────────────────────────────────────────
HOTSPOTS = [
    {
        "category": "pothole",
        "center_latitude": 19.1365,
        "center_longitude": 72.8315,
        "radius_meters": 450.0,
        "issue_count": 5,
        "confidence": 0.89,
        "ward": "K/West",
    },
    {
        "category": "water_leak",
        "center_latitude": 19.0556,
        "center_longitude": 72.8515,
        "radius_meters": 380.0,
        "issue_count": 4,
        "confidence": 0.84,
        "ward": "H/West",
    },
    {
        "category": "sewage",
        "center_latitude": 19.0570,
        "center_longitude": 72.8700,
        "radius_meters": 500.0,
        "issue_count": 3,
        "confidence": 0.76,
        "ward": "H/East",
    },
    {
        "category": "street_light",
        "center_latitude": 19.0600,
        "center_longitude": 72.8370,
        "radius_meters": 300.0,
        "issue_count": 3,
        "confidence": 0.71,
        "ward": "H/West",
    },
]


# ──────────────────────────────────────────────────────────────
# MAIN SEED FUNCTION
# ──────────────────────────────────────────────────────────────
async def seed(session: AsyncSession) -> None:
    print("🌱 Starting Lumen seed data...")

    # ── 1. Categories ──────────────────────────────────────────
    print("  → Seeding categories...")
    cat_map: dict[str, Category] = {}
    for cat_data in CATEGORIES:
        existing = await session.execute(
            select(Category).where(Category.name == cat_data["name"])
        )
        cat = existing.scalar_one_or_none()
        if cat is None:
            cat = Category(**cat_data)
            session.add(cat)
        cat_map[cat_data["name"]] = cat
    await session.flush()

    # ── 2. Badges ──────────────────────────────────────────────
    print("  → Seeding badges...")
    badge_map: dict[str, Badge] = {}
    for badge_data in BADGES:
        existing = await session.execute(
            select(Badge).where(Badge.name == badge_data["name"])
        )
        badge = existing.scalar_one_or_none()
        if badge is None:
            badge = Badge(**badge_data)
            session.add(badge)
        badge_map[badge_data["name"]] = badge
    await session.flush()

    # ── 3. Users ───────────────────────────────────────────────
    print("  → Seeding users...")

    async def get_or_create_user(username: str, data: dict) -> User:
        existing = await session.execute(
            select(User).where(User.username == username)
        )
        u = existing.scalar_one_or_none()
        if u is None:
            u = User(**data)
            session.add(u)
            await session.flush()
        return u

    admin_user = await get_or_create_user(
        "admin",
        {
            "email": "admin@lumen.civic",
            "username": "admin",
            "display_name": "Admin",
            "password_hash": pwd_ctx.hash("admin123"),
            "is_admin": True,
            "is_official": True,
            "department": "BBMP Administration",
            "points": 2500,
            "level": 10,
            "streak_days": 30,
            "privacy_settings": {},
            "notification_preferences": {"email": True, "push": True},
            "created_at": ago(days=90),
            "updated_at": ago(days=1),
        },
    )

    official_user = await get_or_create_user(
        "kiran_bbmp",
        {
            "email": "kiran@bbmp.gov.in",
            "username": "kiran_bbmp",
            "display_name": "Kiran (BBMP Roads)",
            "password_hash": pwd_ctx.hash("official123"),
            "is_official": True,
            "department": "BBMP Roads & Infrastructure",
            "points": 1200,
            "level": 7,
            "streak_days": 14,
            "privacy_settings": {},
            "notification_preferences": {"email": True, "push": True},
            "created_at": ago(days=60),
            "updated_at": ago(days=1),
        },
    )

    reporter_user = await get_or_create_user(
        "priya_bengaluru",
        {
            "email": "priya@example.com",
            "username": "priya_bengaluru",
            "display_name": "Priya Sharma",
            "password_hash": pwd_ctx.hash("citizen123"),
            "points": 850,
            "level": 5,
            "streak_days": 7,
            "pseudonym": "CitizenPriya",
            "privacy_settings": {"show_email": False},
            "notification_preferences": {"email": True, "push": True},
            "created_at": ago(days=45),
            "updated_at": ago(days=1),
        },
    )

    reporter2_user = await get_or_create_user(
        "rajan_civic",
        {
            "email": "rajan@example.com",
            "username": "rajan_civic",
            "display_name": "Rajan Mehta",
            "password_hash": pwd_ctx.hash("citizen123"),
            "points": 640,
            "level": 4,
            "streak_days": 5,
            "pseudonym": "WatchdogRajan",
            "privacy_settings": {},
            "notification_preferences": {"email": False, "push": True},
            "created_at": ago(days=30),
            "updated_at": ago(days=2),
        },
    )

    await session.flush()

    users = {
        "admin": admin_user,
        "official": official_user,
        "reporter": reporter_user,
        "reporter2": reporter2_user,
    }

    # ── 4. Issues ──────────────────────────────────────────────
    print("  → Seeding issues...")
    issue_defs = build_issues(cat_map, users)
    seeded_issues: list[Issue] = []

    for idef in issue_defs:
        existing = await session.execute(
            select(Issue).where(Issue.title == idef["title"])
        )
        issue = existing.scalar_one_or_none()
        if issue is not None:
            seeded_issues.append(issue)
            continue

        reporter_obj: User = idef.pop("reporter")
        category_name: str = idef.pop("category")
        status_transitions: list = idef.pop("status_transitions", [])
        resolved_at_val = idef.pop("resolved_at", None)

        issue = Issue(
            title=idef["title"],
            description=idef["description"],
            category_id=cat_map[category_name].id,
            severity=idef["severity"],
            status=idef["status"],
            latitude=idef["latitude"],
            longitude=idef["longitude"],
            address=idef.get("address"),
            ward=idef.get("ward"),
            zone=idef.get("zone"),
            reporter_id=reporter_obj.id,
            vote_count=idef.get("vote_count", 0),
            verification_count=idef.get("verification_count", 0),
            view_count=idef.get("view_count", 0),
            is_emergency=idef.get("is_emergency", False),
            is_anonymous=False,
            ai_category=idef.get("ai_category"),
            ai_severity=idef.get("ai_severity"),
            ai_confidence=idef.get("ai_confidence"),
            ai_explanation=idef.get("ai_explanation"),
            ai_summary=idef.get("ai_summary"),
            resolution_notes=idef.get("resolution_notes"),
            created_at=idef.get("created_at", now()),
            updated_at=now(),
            resolved_at=resolved_at_val,
            user_correction=False,
        )
        session.add(issue)
        await session.flush()

        # Status history
        for trans in status_transitions:
            hours_ago = trans.get("hours_ago", 0)
            days_ago = trans.get("days_ago", 0)
            changed_at = ago(days=days_ago, hours=hours_ago)
            by_user: User = trans["by"]
            sh = StatusHistory(
                issue_id=issue.id,
                from_status=trans["from_s"],
                to_status=trans["to_s"],
                changed_by=by_user.id,
                changed_at=changed_at,
                note=trans.get("note"),
                is_official=by_user.is_official,
                is_public=True,
            )
            session.add(sh)

        seeded_issues.append(issue)

    await session.flush()

    # ── 5. Verifications ───────────────────────────────────────
    print("  → Seeding verifications...")
    for i, issue in enumerate(seeded_issues[:15]):  # Verify first 15 issues
        for u in [reporter_user, reporter2_user]:
            if str(u.id) == str(issue.reporter_id):
                continue  # Can't verify own issue
            existing = await session.execute(
                select(Verification).where(
                    Verification.issue_id == issue.id,
                    Verification.user_id == u.id,
                )
            )
            if existing.scalar_one_or_none():
                continue
            v = Verification(
                issue_id=issue.id,
                user_id=u.id,
                verification_type="soft" if i % 3 else "hard",
                distance_meters=45.0 + i * 7,
                latitude=issue.latitude + 0.0001,
                longitude=issue.longitude + 0.0001,
                comment="Confirmed this issue." if i % 2 == 0 else None,
                trust_weight=1.5 if u.is_official else 1.0,
                created_at=issue.created_at + timedelta(hours=2),
            )
            session.add(v)
    await session.flush()

    # ── 6. Votes ───────────────────────────────────────────────
    print("  → Seeding votes...")
    for issue in seeded_issues[:20]:
        for u in [reporter_user, reporter2_user, official_user]:
            if str(u.id) == str(issue.reporter_id):
                continue
            existing = await session.execute(
                select(Vote).where(
                    Vote.issue_id == issue.id,
                    Vote.user_id == u.id,
                )
            )
            if existing.scalar_one_or_none():
                continue
            vote = Vote(
                issue_id=issue.id,
                user_id=u.id,
                vote_type="support",
                created_at=issue.created_at + timedelta(hours=1),
            )
            session.add(vote)
    await session.flush()

    # ── 7. Comments ────────────────────────────────────────────
    print("  → Seeding comments...")
    comment_pairs = [
        (seeded_issues[0], reporter2_user, "I saw this pothole swallow an entire scooter wheel. Really dangerous!"),
        (seeded_issues[0], official_user, "Thank you for reporting. Repair crew scheduled for Friday.", True),
        (seeded_issues[5], reporter_user, "This burst pipe has been shooting water for 6 hours now. Please hurry!"),
        (seeded_issues[5], official_user, "Emergency crew is on the way. Please avoid this road.", True),
        (seeded_issues[12], reporter2_user, "I nearly fell into this manhole last night. Someone needs to barricade it."),
        (seeded_issues[3], reporter_user, "Great that this was finally fixed. Let's hope the repair lasts this time!"),
        (seeded_issues[7], official_user, "Water supply restored. A valve was stuck at the pumping station. Sorry for the delay.", True),
        (seeded_issues[20], reporter2_user, "The gang tags are getting worse. They came back and added more."),
    ]
    for row in comment_pairs:
        issue_obj, user_obj, content = row[0], row[1], row[2]
        is_off = row[3] if len(row) > 3 else False
        existing = await session.execute(
            select(Comment).where(
                Comment.issue_id == issue_obj.id,
                Comment.user_id == user_obj.id,
                Comment.content == content,
            )
        )
        if existing.scalar_one_or_none():
            continue
        c = Comment(
            issue_id=issue_obj.id,
            user_id=user_obj.id,
            content=content,
            is_official=is_off,
            is_pinned=is_off,
            is_deleted=False,
            created_at=issue_obj.created_at + timedelta(hours=3),
        )
        session.add(c)
    await session.flush()

    # ── 8. Leaderboard Points ──────────────────────────────────
    print("  → Seeding leaderboard points...")
    lp_entries = [
        (reporter_user, "reported", 20),
        (reporter_user, "verified", 10),
        (reporter_user, "streak_bonus", 50),
        (reporter_user, "resolved_confirmed", 30),
        (reporter2_user, "reported", 20),
        (reporter2_user, "verified", 10),
        (official_user, "status_update", 5),
        (admin_user, "admin_action", 0),
    ]
    for u, action, pts in lp_entries:
        lp = LeaderboardPoints(
            user_id=u.id,
            action=action,
            points=pts,
            created_at=ago(days=1),
        )
        session.add(lp)
    await session.flush()

    # ── 9. User Badges ─────────────────────────────────────────
    print("  → Seeding user badges...")
    badge_assignments = [
        (reporter_user, "first_report"),
        (reporter_user, "reporter_10"),
        (reporter_user, "impact_100"),
        (reporter_user, "streak_7"),
        (reporter_user, "emergency_reporter"),
        (reporter2_user, "first_report"),
        (reporter2_user, "verified_5"),
        (reporter2_user, "impact_100"),
        (official_user, "resolution_confirmed"),
        (admin_user, "impact_500"),
    ]
    for u, badge_name in badge_assignments:
        if badge_name not in badge_map:
            continue
        existing = await session.execute(
            select(UserBadge).where(
                UserBadge.user_id == u.id,
                UserBadge.badge_id == badge_map[badge_name].id,
            )
        )
        if existing.scalar_one_or_none():
            continue
        ub = UserBadge(
            user_id=u.id,
            badge_id=badge_map[badge_name].id,
            earned_at=ago(days=2),
        )
        session.add(ub)
    await session.flush()

    # ── 10. Predictive Hotspots ────────────────────────────────
    print("  → Seeding predictive hotspots...")
    existing_hotspots = await session.execute(select(PredictiveHotspot))
    if not existing_hotspots.scalars().all():
        from datetime import date as date_type
        next_week = (now() + timedelta(days=7)).date()
        for hs in HOTSPOTS:
            h = PredictiveHotspot(
                **hs,
                predicted_next_issue_date=next_week,
                generated_at=now(),
            )
            session.add(h)
        await session.flush()

    await session.commit()
    print("\n✅ Seed data loaded successfully.")
    print(f"   Categories:  {len(CATEGORIES)}")
    print(f"   Badges:      {len(BADGES)}")
    print(f"   Users:       4 (admin, official, priya, rajan)")
    print(f"   Issues:      {len(issue_defs)} across multiple categories")
    print(f"   Hotspots:    {len(HOTSPOTS)}")
    print("\n🔑 Login credentials:")
    print("   admin@lumen.civic     / admin123")
    print("   kiran@bbmp.gov.in     / official123")
    print("   priya@example.com     / citizen123")
    print("   rajan@example.com     / citizen123")


async def main() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
