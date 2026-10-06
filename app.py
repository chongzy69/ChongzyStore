from flask import Flask, render_template, request, redirect, url_for, session, Response

from flask_sqlalchemy import SQLAlchemy

from werkzeug.utils import secure_filename

from werkzeug.security import generate_password_hash, check_password_hash



import os

import uuid

import requests

import razorpay

import re



from datetime import datetime





# =========================================================

# APP CONFIGURATION

# =========================================================



app = Flask(__name__)



app.config["SECRET_KEY"] = "CHANGE_THIS_SECRET_KEY_LATER"



app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chongzystore.db"



app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False



app.config["UPLOAD_FOLDER"] = "static/uploads"



db = SQLAlchemy(app)



os.makedirs(

    app.config["UPLOAD_FOLDER"],

    exist_ok=True

)





# =========================================================

# RAZORPAY

# =========================================================



RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")

RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")



razorpay_client = None



if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:



    razorpay_client = razorpay.Client(

        auth=(

            RAZORPAY_KEY_ID,

            RAZORPAY_KEY_SECRET

        )

    )



# =========================================================

# ARCADEZY API

# =========================================================



ARCADEZY_API_KEY = os.environ.get("ARCADEZY_API_KEY")



ARCADEZY_BASE_URL = "https://arcadezy.com/api/v1"

ARCADEZY_MLBB_SLUG = "mobile-legends-global"



# =========================================================

# ARCADEZY FUNCTIONS

# =========================================================



def arcadezy_headers():



    if not ARCADEZY_API_KEY:

        raise Exception("ARCADEZY_API_KEY is not configured.")



    return {

        "X-API-Key": ARCADEZY_API_KEY,

        "Content-Type": "application/json"

    }





def arcadezy_get_offers(slug=None):
    """
    Get the current MLBB offers from Arcadezy.
    """

    if slug is None:
        slug = ARCADEZY_MLBB_SLUG

    response = requests.get(
        f"{ARCADEZY_BASE_URL}/categories/"
        f"{slug}/offers",
        headers=arcadezy_headers(),
        timeout=20
    )

    return response



def arcadezy_validate_player(

    player_id,

    server_id

):



    response = requests.post(

        f"{ARCADEZY_BASE_URL}/categories/"

        f"{ARCADEZY_MLBB_SLUG}/validate-id",

        headers=arcadezy_headers(),

        json={

            "fields": {

                "player_id": str(player_id),

                "server_id": str(server_id)

            }

        },

        timeout=20

    )



    return response





def arcadezy_create_order(

    offer_id,

    player_id,

    server_id,

    idempotency_key

):



    response = requests.post(

        f"{ARCADEZY_BASE_URL}/orders",

        headers={

            **arcadezy_headers(),

            "Idempotency-Key": idempotency_key

        },

        json={

            "offer_id": str(offer_id),

            "qty": 1,

            "fields": {

                "player_id": str(player_id),

                "server_id": str(server_id)

            }

        },

        timeout=30

    )



    return response

def arcadezy_get_order(arcadezy_order_id):
    response = requests.get(
        f"{ARCADEZY_BASE_URL}/orders/{arcadezy_order_id}",
        headers=arcadezy_headers(),
        timeout=20
    )
    return response

# =========================================================
# ARCADEZY - IMPORT REAL MLBB PRODUCTS
# =========================================================

@app.route(
    "/admin/import-arcadezy",
    methods=["POST"]
)
def import_arcadezy():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    try:

        # -------------------------------------------------
        # STEP 1: GET MOBILE LEGENDS CATEGORIES
        # -------------------------------------------------

        categories = []

        page = 1

        while page <= 20:

            response = requests.get(
                f"{ARCADEZY_BASE_URL}/categories",
                headers=arcadezy_headers(),
                params={
                    "type": "topup",
                    "q": "mobile legends",
                    "page": page,
                    "sort": "lo"
                },
                timeout=20
            )

            if response.status_code != 200:

                try:
                    error_data = response.json()
                except Exception:
                    error_data = {}

                return (
                    "Arcadezy category error: "
                    + str(
                        error_data.get(
                            "error",
                            response.text
                        )
                    ),
                    response.status_code
                )

            data = response.json()

            # ---------------------------------------------
            # HANDLE DIFFERENT ARCADEZY RESPONSE FORMATS
            # ---------------------------------------------

            page_categories = []

            if isinstance(data, list):

                page_categories = data

            elif isinstance(data, dict):

                if isinstance(
                    data.get("categories"),
                    list
                ):
                    page_categories = data["categories"]

                elif isinstance(
                    data.get("items"),
                    list
                ):
                    page_categories = data["items"]

                elif isinstance(
                    data.get("results"),
                    list
                ):
                    page_categories = data["results"]

                elif isinstance(
                    data.get("data"),
                    list
                ):
                    page_categories = data["data"]

                elif isinstance(
                    data.get("data"),
                    dict
                ):

                    inner = data["data"]

                    if isinstance(
                        inner.get("categories"),
                        list
                    ):
                        page_categories = (
                            inner["categories"]
                        )

                    elif isinstance(
                        inner.get("items"),
                        list
                    ):
                        page_categories = (
                            inner["items"]
                        )

            if not page_categories:
                break

            categories.extend(
                page_categories
            )

            # If less than a full page was returned,
            # there is probably no next page.
            if len(page_categories) < 48:
                break

            page += 1

        # -------------------------------------------------
        # STEP 2: KEEP ONLY MLBB CATEGORIES
        # -------------------------------------------------

        mlbb_categories = {}

        for category in categories:

            if not isinstance(
                category,
                dict
            ):
                continue

            slug = str(
                category.get(
                    "slug",
                    ""
                )
            ).strip()

            name = str(
                category.get(
                    "name",
                    ""
                )
            ).strip()

            category_type = str(
                category.get(
                    "type",
                    "topup"
                )
            ).lower()

            if not slug:
                continue

            text = (
                slug + " " + name
            ).lower()

            if (
                (
                "mobile-legends" in text
                or "mobile legends" in text
            )   
            and category_type == "topup"
            ):
                

                mlbb_categories[
                    slug
                ] = category

        if not mlbb_categories:

            return (
                """
                <h2>No Mobile Legends categories found.</h2>

                <p>
                Please check the Arcadezy API response.
                </p>

                <br>

                <a href="/admin/dashboard">
                    Back to Dashboard
                </a>
                """,
                400
            )

        # -------------------------------------------------
        # STEP 3: REMOVE OLD IMPORTED PACKAGES
        # -------------------------------------------------

        old_packages = RegionPackage.query.all()

        removed_old = len(
            old_packages
        )

        for package in old_packages:
            db.session.delete(package)

        db.session.commit()

        # -------------------------------------------------
        # STEP 4: IMPORT REAL OFFERS
        # -------------------------------------------------

        imported = 0
        skipped = 0
        regions_created = 0

        imported_regions = []

        for slug, category in mlbb_categories.items():

            # ---------------------------------------------
            # GET REGION NAME
            # ---------------------------------------------

            category_name = str(
                category.get(
                    "name",
                    slug
                )
            ).strip()

            region_name = category_name

            # Example:
            # Mobile Legends (Global)
            # becomes:
            # Global

            match = re.search(
                r"\((.*?)\)",
                category_name
            )

            if match:

                region_name = (
                    match.group(1)
                    .strip()
                )

            else:

                region_name = re.sub(
                    r"mobile\s*legends",
                    "",
                    category_name,
                    flags=re.IGNORECASE
                ).strip()

                region_name = (
                    region_name
                    .strip("- ")
                )

            if not region_name:
                region_name = "Global"

            # ---------------------------------------------
            # FIND / CREATE REGION
            # ---------------------------------------------

            region = Region.query.filter_by(
                name=region_name
            ).first()

            if not region:

                region = Region(
                    name=region_name,
                    code=(
                        region_name
                        .upper()
                        .replace(" ", "_")
                    )
                )

                db.session.add(
                    region
                )

                db.session.flush()

                regions_created += 1

            imported_regions.append(
                region_name
            )

            # ---------------------------------------------
            # GET OFFERS FOR THIS REGION
            # ---------------------------------------------

            offers_response = requests.get(
                f"{ARCADEZY_BASE_URL}/categories/"
                f"{slug}/offers",
                headers=arcadezy_headers(),
                timeout=20
            )

            if offers_response.status_code != 200:

                print(
                    "Arcadezy offers error:",
                    slug,
                    offers_response.text
                )

                continue

            offers_data = (
                offers_response.json()
            )

            offers = []

            if isinstance(
                offers_data,
                dict
            ):

                if isinstance(
                    offers_data.get("offers"),
                    list
                ):
                    offers = (
                        offers_data["offers"]
                    )

                elif isinstance(
                    offers_data.get("data"),
                    dict
                ):

                    if isinstance(
                        offers_data[
                            "data"
                        ].get("offers"),
                        list
                    ):
                        offers = (
                            offers_data[
                                "data"
                            ]["offers"]
                        )

            elif isinstance(
                offers_data,
                list
            ):
                offers = offers_data

            # ---------------------------------------------
            # PROCESS OFFERS
            # ---------------------------------------------

            for offer in offers:

                if not isinstance(
                    offer,
                    dict
                ):
                    skipped += 1
                    continue

                # -----------------------------------------
                # REAL ARCADEZY OFFER ID
                # -----------------------------------------

                offer_id = str(
                    offer.get(
                        "offer_id",
                        offer.get(
                            "id",
                            ""
                        )
                    )
                ).strip()

                if not offer_id:

                    skipped += 1
                    continue

                # -----------------------------------------
                # PRODUCT NAME
                # -----------------------------------------

                offer_name = str(
                    offer.get(
                        "name",
                        offer.get(
                            "title",
                            ""
                        )
                    )
                ).strip()

                if not offer_name:

                    skipped += 1
                    continue

                # -----------------------------------------
                # ONLY DIAMOND PRODUCTS
                # -----------------------------------------

                if "diamond" not in (
                    offer_name.lower()
                ):

                    skipped += 1
                    continue

                # -----------------------------------------
                # EXTRACT DIAMONDS
                #
                # Example:
                # 5 Diamonds = 5
                # 10 + 1 Diamonds = 11
                # 20 + 2 Diamonds = 22
                # -----------------------------------------

                numbers = re.findall(
                    r"\d[\d,]*",
                    offer_name
                )

                if not numbers:

                    skipped += 1
                    continue

                try:

                    diamond_values = [
                        int(
                            number.replace(
                                ",",
                                ""
                            )
                        )
                        for number in numbers
                    ]

                    diamonds = sum(
                        diamond_values
                    )

                except Exception:

                    skipped += 1
                    continue

                if diamonds <= 0:

                    skipped += 1
                    continue

                # -----------------------------------------
                # SUPPLIER PRICE
                # -----------------------------------------

                supplier_price = offer.get(
                    "price_usd"
                )

                if supplier_price is None:

                    supplier_price = offer.get(
                        "price"
                    )

                try:

                    supplier_price = float(
                        supplier_price
                        or 0
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    supplier_price = 0

                # -----------------------------------------
                # CREATE PACKAGE
                # -----------------------------------------

                package = RegionPackage(
                    region_id=region.id,
                    package_name=offer_name,
                    diamonds=diamonds,
                    price=0,
                    arcadezy_offer_id=offer_id,
                    arcadezy_price_usd=(
                        supplier_price
                    ),
                    arcadezy_category_slug=slug,
                    active=False
                )

                db.session.add(
                    package
                )

                imported += 1

        # -------------------------------------------------
        # SAVE EVERYTHING
        # -------------------------------------------------

        db.session.commit()

        # Remove duplicate region names from display
        imported_regions = list(
            dict.fromkeys(
                imported_regions
            )
        )

        # -------------------------------------------------
        # RESULT PAGE
        # -------------------------------------------------

        return f"""
        <!DOCTYPE html>

        <html>

        <head>

            <title>
                Arcadezy Import Complete
            </title>

            <style>

                body {{
                    background:#080d1c;
                    color:white;
                    font-family:Arial,sans-serif;
                    padding:50px;
                }}

                .box {{
                    max-width:800px;
                    margin:auto;
                    background:#121a30;
                    padding:40px;
                    border-radius:20px;
                }}

                h1 {{
                    color:#00d9ff;
                }}

                .number {{
                    font-size:32px;
                    font-weight:bold;
                    color:#00ff99;
                }}

                .item {{
                    margin:12px 0;
                    padding:15px;
                    background:#1a2440;
                    border-radius:10px;
                }}

                a {{
                    display:inline-block;
                    margin-top:25px;
                    margin-right:10px;
                    padding:14px 22px;
                    background:#00bfff;
                    color:white;
                    text-decoration:none;
                    border-radius:10px;
                    font-weight:bold;
                }}

            </style>

        </head>

        <body>

            <div class="box">

                <h1>
                    ✅ Arcadezy Import Complete
                </h1>

                <div class="item">
                    Old packages removed:
                    <span class="number">
                        {removed_old}
                    </span>
                </div>

                <div class="item">
                    New valid diamond packages:
                    <span class="number">
                        {imported}
                    </span>
                </div>

                <div class="item">
                    Regions found:
                    <span class="number">
                        {len(imported_regions)}
                    </span>
                </div>

                <div class="item">
                    New regions created:
                    <span class="number">
                        {regions_created}
                    </span>
                </div>

                <div class="item">
                    Products skipped:
                    <span class="number">
                        {skipped}
                    </span>
                </div>

                <h3>
                    Regions:
                </h3>

                <p>
                    {" • ".join(imported_regions)}
                </p>

                <p>
                    All imported products are currently
                    <strong>INACTIVE</strong>.
                </p>

                <p>
                    This is intentional.
                    We will set your ChongzyStore
                    selling prices before customers
                    can purchase them.
                </p>

                <a href="/admin/manage-packages">
                    📦 Manage Packages
                </a>

                <a href="/admin/dashboard">
                    ← Dashboard
                </a>

            </div>

        </body>

        </html>
        """

    except Exception as e:

        db.session.rollback()

        print(
            "ARCADEZY IMPORT ERROR:",
            str(e)
        )

        return (
            "Arcadezy import failed: "
            + str(e),
            500
        )
    # =========================================================
# ARCADEZY - TEST OFFERS CONNECTION
# =========================================================

@app.route("/admin/arcadezy-test")
def arcadezy_test():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    try:

        response = arcadezy_get_offers()

        try:
            data = response.json()
        except Exception:
            data = {
                "raw_response": response.text
            }

        return {
            "success": response.ok,
            "http_status": response.status_code,
            "arcadezy_response": data
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }, 500

    

# =========================================================
# ARCADEZY - VALIDATE MLBB PLAYER
# =========================================================

@app.route("/api/validate-mlbb", methods=["POST"])
def validate_mlbb():

    if not session.get("user_id"):
        return {
            "success": False,
            "message": "Please login first."
        }, 401

    player_id = request.form.get(
        "player_id",
        ""
    ).strip()

    server_id = request.form.get(
        "server_id",
        ""
    ).strip()

    if not player_id or not server_id:
        return {
            "success": False,
            "message": "Please enter Player ID and Server ID."
        }, 400

    try:

        response = arcadezy_validate_player(
            player_id,
            server_id
        )

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code == 200:

            if data.get("ok") is False:

                return {
                    "success": False,
                    "message": data.get(
                        "error",
                        "Unable to validate this account."
                    )
                }, 400

            if data.get("supported") is False:

                return {
                    "success": False,
                    "message": "MLBB ID validation is currently unavailable."
                }, 400

            if data.get("valid") is False:

                return {
                    "success": False,
                    "message": "Account not found. Please check your Player ID and Server ID."
                }, 400

            return {
                "success": True,
                "player_name": data.get(
                    "player_name",
                    "Unknown"
                ),
                "region": data.get(
                    "region",
                    "Unknown"
                )
            }, 200

        if response.status_code == 503:

            return {
                "success": False,
                "message": "MLBB verification is temporarily unavailable. Please try again."
            }, 503

        if response.status_code == 429:

            return {
                "success": False,
                "message": "Too many verification attempts. Please wait a moment and try again."
            }, 429

        return {
            "success": False,
            "message": data.get(
                "error",
                "Unable to validate the MLBB account."
            )
        }, response.status_code

    except Exception as e:

        print(
            "Arcadezy validation error:",
            str(e)
        )

        return {
            "success": False,
            "message": "Unable to connect to the MLBB verification service."
        }, 500



# =========================================================

# DATABASE MODELS

# =========================================================



class User(db.Model):



    id = db.Column(

        db.Integer,

        primary_key=True

    )



    name = db.Column(

        db.String(100),

        nullable=False

    )



    email = db.Column(

        db.String(150),

        unique=True,

        nullable=True

    )



    phone = db.Column(

        db.String(30),

        unique=True,

        nullable=True

    )



    password = db.Column(

        db.String(255),

        nullable=False

    )



    coins = db.Column(

        db.Integer,

        nullable=False,

        default=0

    )



    created_at = db.Column(

        db.DateTime,

        server_default=db.func.now()

    )





class Account(db.Model):



    id = db.Column(

        db.Integer,

        primary_key=True

    )



    title = db.Column(

        db.String(200),

        nullable=False

    )



    price = db.Column(

        db.Float,

        nullable=False,

        default=0

    )



    usd_price = db.Column(

        db.Float,

        nullable=False,

        default=0

    )



    rank = db.Column(

        db.String(100)

    )



    level = db.Column(

        db.String(50)

    )



    skins = db.Column(

        db.String(100)

    )



    heroes = db.Column(

        db.String(100)

    )



    description = db.Column(

        db.Text

    )



    image = db.Column(

        db.String(300)

    )



    status = db.Column(

        db.String(50),

        default="Available"

    )





class AccountInquiry(db.Model):



    id = db.Column(

        db.Integer,

        primary_key=True

    )



    account_id = db.Column(

        db.Integer,

        db.ForeignKey("account.id"),

        nullable=False

    )



    customer_name = db.Column(

        db.String(100),

        nullable=False

    )



    customer_phone = db.Column(

        db.String(30),

        nullable=False

    )



    customer_email = db.Column(

        db.String(150),

        nullable=True

    )



    message = db.Column(

        db.Text,

        nullable=True

    )



    # FIX: status was missing

    status = db.Column(

        db.String(50),

        default="Pending"

    )



    created_at = db.Column(

        db.DateTime,

        server_default=db.func.now()

    )



    account = db.relationship(

        "Account",

        backref="inquiries"

    )





class Region(db.Model):



    id = db.Column(

        db.Integer,

        primary_key=True

    )



    name = db.Column(

        db.String(100),

        nullable=False,

        unique=True

    )



    code = db.Column(

        db.String(50),

        nullable=False

    )



    packages = db.relationship(

        "RegionPackage",

        backref="region",

        cascade="all, delete-orphan"

    )





class CoinTransaction(db.Model):



    id = db.Column(

        db.Integer,

        primary_key=True

    )



    transaction_number = db.Column(

        db.String(50),

        unique=True,

        nullable=False

    )



    user_id = db.Column(

        db.Integer,

        db.ForeignKey("user.id"),

        nullable=False

    )



    coins = db.Column(

        db.Integer,

        nullable=False

    )



    transaction_type = db.Column(

        db.String(50),

        nullable=False,

        default="Purchase"

    )



    amount = db.Column(

        db.Float,

        nullable=False

    )



    status = db.Column(

        db.String(50),

        default="Pending"

    )



    razorpay_order_id = db.Column(

        db.String(100),

        nullable=True

    )



    razorpay_payment_id = db.Column(

        db.String(100),

        nullable=True

    )



    paid_at = db.Column(

        db.DateTime,

        nullable=True

    )







    created_at = db.Column(

        db.DateTime,

        server_default=db.func.now()

    )



    user = db.relationship(

        "User",

        backref="coin_transactions"

    )





class RegionPackage(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    region_id = db.Column(
        db.Integer,
        db.ForeignKey("region.id"),
        nullable=False
    )

    # Product name exactly as Arcadezy provides it
    package_name = db.Column(
        db.String(200),
        nullable=True
    )

    # Number of diamonds
    diamonds = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    # ChongzyStore selling price in INR
    price = db.Column(
        db.Float,
        nullable=False,
        default=0
    )

    # Arcadezy supplier offer UUID
    arcadezy_offer_id = db.Column(
        db.String(150),
        nullable=True
    )

    # Arcadezy supplier price in USD
    arcadezy_price_usd = db.Column(
        db.Float,
        nullable=True
    )

    # Arcadezy category slug
    arcadezy_category_slug = db.Column(
        db.String(150),
        nullable=True
    )

    active = db.Column(
        db.Boolean,
        default=False
    )

class Order(db.Model):



    id = db.Column(

        db.Integer,

        primary_key=True

    )



    order_number = db.Column(

        db.String(50),

        unique=True,

        nullable=False

    )



    user_id = db.Column(

        db.Integer,

        db.ForeignKey("user.id"),

        nullable=False

    )



    package_id = db.Column(

        db.Integer,

        db.ForeignKey("region_package.id"),

        nullable=False

    )



    region_name = db.Column(

        db.String(100),

        nullable=False

    )



    diamonds = db.Column(

        db.Integer,

        nullable=False

    )



    price = db.Column(

        db.Float,

        nullable=False

    )



    mlbb_user_id = db.Column(

        db.String(100),

        nullable=False

    )



    zone_id = db.Column(

        db.String(100),

        nullable=False

    )



    phone = db.Column(

        db.String(30)

    )



    status = db.Column(

        db.String(50),

        default="Pending"

    )



    # FIX: payment_method was missing

    payment_method = db.Column(

        db.String(30),

        default="razorpay"

    )



    razorpay_order_id = db.Column(

        db.String(100),

        nullable=True

    )



    razorpay_payment_id = db.Column(

        db.String(100),

        nullable=True

    )



    paid_at = db.Column(

        db.DateTime,

        nullable=True

    )







    # Arcadezy supplier fields
    arcadezy_order_id = db.Column(

        db.String(100),

        nullable=True

    )



    arcadezy_offer_id = db.Column(

        db.String(100),

        nullable=True

    )



    arcadezy_idempotency_key = db.Column(

        db.String(100),

        unique=True,

        nullable=True

    )



    arcadezy_status = db.Column(

        db.String(50),

        nullable=True

    )



    arcadezy_error = db.Column(

        db.Text,

        nullable=True

    )



    created_at = db.Column(

        db.DateTime,

        server_default=db.func.now()

    )



    user = db.relationship(

        "User",

        backref="orders"

    )



    package = db.relationship(

        "RegionPackage"

    )





# =========================================================

# DATABASE SETUP + SAFE MIGRATION

# =========================================================



with app.app_context():



    db.create_all()



    # -----------------------------------------------------

    # ORDER TABLE MIGRATION

    # -----------------------------------------------------



    order_columns = db.session.execute(

        db.text('PRAGMA table_info("order")')

    ).fetchall()



    order_column_names = [

        row[1]

        for row in order_columns

    ]



    if "payment_method" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN payment_method VARCHAR(30) '

                'DEFAULT "razorpay"'

            )

        )



    if "razorpay_order_id" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN razorpay_order_id VARCHAR(100)'

            )

        )



    if "razorpay_payment_id" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN razorpay_payment_id VARCHAR(100)'

            )

        )



    if "paid_at" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN paid_at DATETIME'

            )

        )



    if "arcadezy_order_id" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN arcadezy_order_id VARCHAR(100)'

            )

        )



    if "arcadezy_offer_id" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN arcadezy_offer_id VARCHAR(100)'

            )

        )



    if "arcadezy_idempotency_key" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN arcadezy_idempotency_key VARCHAR(100)'

            )

        )



    if "arcadezy_status" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN arcadezy_status VARCHAR(50)'

            )

        )



    if "arcadezy_error" not in order_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "order" '

                'ADD COLUMN arcadezy_error TEXT'

            )

        )



    db.session.commit()

        # -----------------------------------------------------
    # REGION PACKAGE MIGRATION
    # -----------------------------------------------------

    region_package_columns = db.session.execute(
        db.text(
            'PRAGMA table_info("region_package")'
        )
    ).fetchall()

    region_package_column_names = [
        row[1]
        for row in region_package_columns
    ]

    if "package_name" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN package_name VARCHAR(200)'
            )
        )

    if "arcadezy_offer_id" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN arcadezy_offer_id VARCHAR(150)'
            )
        )

    if "arcadezy_price_usd" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN arcadezy_price_usd FLOAT'
            )
        )

    db.session.commit()

        # -----------------------------------------------------
    # REGION PACKAGE ARCADEZY MIGRATION
    # -----------------------------------------------------

    region_package_columns = db.session.execute(
        db.text(
            'PRAGMA table_info("region_package")'
        )
    ).fetchall()

    region_package_column_names = [
        row[1]
        for row in region_package_columns
    ]

    if "package_name" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN package_name VARCHAR(200)'
            )
        )

    if "arcadezy_offer_id" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN arcadezy_offer_id VARCHAR(150)'
            )
        )

    if "arcadezy_price_usd" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN arcadezy_price_usd FLOAT'
            )
        )

    if "arcadezy_category_slug" not in region_package_column_names:

        db.session.execute(
            db.text(
                'ALTER TABLE "region_package" '
                'ADD COLUMN arcadezy_category_slug VARCHAR(150)'
            )
        )

    db.session.commit()







    # -----------------------------------------------------

    # COIN TRANSACTION TABLE

    # -----------------------------------------------------



    coin_columns = db.session.execute(

        db.text(

            'PRAGMA table_info("coin_transaction")'

        )

    ).fetchall()



    coin_column_names = [

        row[1]

        for row in coin_columns

    ]



    if "transaction_type" not in coin_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "coin_transaction" '

                'ADD COLUMN transaction_type '

                'VARCHAR(50) DEFAULT "Purchase"'

            )

        )



    db.session.commit()



    # -----------------------------------------------------

    # USER TABLE

    # -----------------------------------------------------



    user_columns = db.session.execute(

        db.text(

            "PRAGMA table_info(user)"

        )

    ).fetchall()



    user_column_names = [

        row[1]

        for row in user_columns

    ]



    if "coins" not in user_column_names:



        db.session.execute(

            db.text(

                "ALTER TABLE user "

                "ADD COLUMN coins INTEGER DEFAULT 0"

            )

        )



    db.session.commit()



    # -----------------------------------------------------

    # ACCOUNT TABLE

    # -----------------------------------------------------



    account_columns = db.session.execute(

        db.text(

            "PRAGMA table_info(account)"

        )

    ).fetchall()



    account_column_names = [

        row[1]

        for row in account_columns

    ]



    if "usd_price" not in account_column_names:



        db.session.execute(

            db.text(

                "ALTER TABLE account "

                "ADD COLUMN usd_price FLOAT DEFAULT 0"

            )

        )



    db.session.commit()



    # -----------------------------------------------------

    # ACCOUNT INQUIRY TABLE

    # -----------------------------------------------------



    inquiry_columns = db.session.execute(

        db.text(

            'PRAGMA table_info("account_inquiry")'

        )

    ).fetchall()



    inquiry_column_names = [

        row[1]

        for row in inquiry_columns

    ]



    if "status" not in inquiry_column_names:



        db.session.execute(

            db.text(

                'ALTER TABLE "account_inquiry" '

                'ADD COLUMN status VARCHAR(50) '

                'DEFAULT "Pending"'

            )

        )



    db.session.commit()

        # -----------------------------------------------------
    # ADD ARCADEZY OFFER ID TO REGION PACKAGE TABLE
    # -----------------------------------------------------

    region_package_columns = db.session.execute(
        db.text(
            "PRAGMA table_info(region_package)"
        )
    ).fetchall()

    region_package_column_names = [
        row[1]
        for row in region_package_columns
    ]

    if (
        region_package_columns
        and "arcadezy_offer_id"
        not in region_package_column_names
    ):

        print(
            "Adding arcadezy_offer_id column "
            "to region_package table..."
        )

        db.session.execute(
            db.text(
                "ALTER TABLE region_package "
                "ADD COLUMN arcadezy_offer_id VARCHAR(100)"
            )
        )

        db.session.commit()

        print(
            "arcadezy_offer_id column "
            "added successfully."
        )

            # -----------------------------------------------------
    # ADD PACKAGE NAME TO REGION PACKAGE TABLE
    # -----------------------------------------------------

    region_package_columns = db.session.execute(
        db.text(
            "PRAGMA table_info(region_package)"
        )
    ).fetchall()

    region_package_column_names = [
        row[1]
        for row in region_package_columns
    ]

    if (
        region_package_columns
        and "package_name"
        not in region_package_column_names
    ):

        print(
            "Adding package_name column "
            "to region_package table..."
        )

        db.session.execute(
            db.text(
                "ALTER TABLE region_package "
                "ADD COLUMN package_name VARCHAR(200)"
            )
        )

        db.session.commit()

        print(
            "package_name column "
            "added successfully."
        )
    



    print("Database setup complete.")





# =========================================================

# CUSTOMER PAGES

# =========================================================



@app.route("/terms")

def terms():

    return render_template("terms.html")





@app.route("/privacy")

def privacy():

    return render_template("privacy.html")





@app.route("/refund")

def refund():

    return render_template("refund.html")





@app.route("/faq")

def faq():

    return render_template("faq.html")

# =========================================================
# REMOVE ADVENTURE REGIONS
# =========================================================

@app.route(
    "/admin/remove-adventure-regions",
    methods=["POST"]
)
def remove_adventure_regions():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    try:

        adventure_regions = Region.query.filter(
            db.or_(
                Region.name.ilike("%adventure%"),
                Region.code.ilike("%adventure%")
            )
        ).all()

        removed = 0

        for region in adventure_regions:

            db.session.delete(region)
            removed += 1

        db.session.commit()

        return f"""
        <html>
        <head>
            <title>Adventure Removed</title>

            <style>

                body {{
                    background:#080d18;
                    color:white;
                    font-family:Arial;
                    text-align:center;
                    padding:80px;
                }}

                .box {{
                    max-width:600px;
                    margin:auto;
                    background:#111827;
                    padding:40px;
                    border-radius:20px;
                }}

                h1 {{
                    color:#00e676;
                }}

                .number {{
                    font-size:50px;
                    color:#00e676;
                    font-weight:bold;
                }}

                a {{
                    display:inline-block;
                    margin-top:25px;
                    padding:14px 25px;
                    background:#ffd000;
                    color:#000;
                    text-decoration:none;
                    border-radius:10px;
                    font-weight:bold;
                }}

            </style>
        </head>

        <body>

            <div class="box">

                <h1>
                    ✓ Adventure Regions Removed
                </h1>

                <div class="number">
                    {removed}
                </div>

                <p>
                    Adventure region(s) were removed.
                </p>

                <p>
                    Normal MLBB regions were not removed.
                </p>

                <a href="/">
                    View ChongzyStore
                </a>

            </div>

        </body>
        </html>
        """

    except Exception as e:

        db.session.rollback()

        print(
            "Adventure region removal error:",
            e
        )

        return (
            "Unable to remove Adventure regions.",
            500
        )




@app.route("/")
def home():

    all_regions = Region.query.order_by(
        Region.name.asc()
    ).all()

    # Remove duplicate region names from display
    regions = []
    seen_regions = set()

    for region in all_regions:

        region_key = (
            region.name
            .strip()
            .lower()
        )

        if region_key in seen_regions:
            continue

        seen_regions.add(
            region_key
        )

        regions.append(
            region
        )

    accounts = Account.query.filter_by(
        status="Available"
    ).all()

    return render_template(
        "index.html",
        regions=regions,
        accounts=accounts
    )


# =========================================================

# ACCOUNT DETAILS

# =========================================================



@app.route("/account-details/<int:account_id>")

def account_details(account_id):



    account = Account.query.get_or_404(

        account_id

    )



    return render_template(

        "account_details.html",

        account=account

    )





# =========================================================

# ACCOUNT INQUIRY

# =========================================================



@app.route(

    "/account-inquiry/<int:account_id>",

    methods=["GET", "POST"]

)

def account_inquiry(account_id):



    account = Account.query.get_or_404(

        account_id

    )



    if account.status != "Available":



        return render_template(

            "account_inquiry.html",

            account=account,

            error="Sorry, this account is no longer available."

        )



    if request.method == "POST":



        customer_name = request.form.get(

            "customer_name",

            ""

        ).strip()



        customer_phone = request.form.get(

            "customer_phone",

            ""

        ).strip()



        customer_email = request.form.get(

            "customer_email",

            ""

        ).strip()



        message = request.form.get(

            "message",

            ""

        ).strip()



        if not customer_name:



            return render_template(

                "account_inquiry.html",

                account=account,

                error="Please enter your name."

            )



        if not customer_phone:



            return render_template(

                "account_inquiry.html",

                account=account,

                error="Please enter your phone number."

            )



        inquiry = AccountInquiry(

            account_id=account.id,

            customer_name=customer_name,

            customer_phone=customer_phone,

            customer_email=(

                customer_email

                if customer_email

                else None

            ),

            message=message,

            status="Pending"

        )



        db.session.add(inquiry)

        db.session.commit()



        return render_template(

            "account_inquiry_success.html",

            inquiry=inquiry,

            account=account

        )



    return render_template(

        "account_inquiry.html",

        account=account

    )





# =========================================================

# REGISTER

# =========================================================



@app.route(

    "/register",

    methods=["GET", "POST"]

)

def register():



    if request.method == "POST":



        name = request.form.get(

            "name",

            ""

        ).strip()



        email = request.form.get(

            "email",

            ""

        ).strip().lower()



        phone = request.form.get(

            "phone",

            ""

        ).strip()



        password = request.form.get(

            "password",

            ""

        )



        confirm_password = request.form.get(

            "confirm_password",

            ""

        )



        if not name:



            return render_template(

                "register.html",

                error="Please enter your name."

            )



        if not email and not phone:



            return render_template(

                "register.html",

                error="Please enter an email or phone number."

            )



        if len(password) < 6:



            return render_template(

                "register.html",

                error="Password must be at least 6 characters."

            )



        if password != confirm_password:



            return render_template(

                "register.html",

                error="Passwords do not match."

            )



        if email:



            existing_email = User.query.filter_by(

                email=email

            ).first()



            if existing_email:



                return render_template(

                    "register.html",

                    error="This email is already registered."

                )



        if phone:



            existing_phone = User.query.filter_by(

                phone=phone

            ).first()



            if existing_phone:



                return render_template(

                    "register.html",

                    error="This phone number is already registered."

                )



        new_user = User(

            name=name,

            email=email if email else None,

            phone=phone if phone else None,

            password=generate_password_hash(

                password

            ),

            coins=0

        )



        db.session.add(new_user)

        db.session.commit()



        session["user_id"] = new_user.id

        session["user_name"] = new_user.name



        return redirect(

            url_for("customer_dashboard")

        )



    return render_template(

        "register.html"

    )





# =========================================================

# LOGIN

# =========================================================



@app.route(

    "/login",

    methods=["GET", "POST"]

)

def login():



    if request.method == "POST":



        login_value = request.form.get(

            "login",

            ""

        ).strip().lower()



        password = request.form.get(

            "password",

            ""

        )



        user = User.query.filter_by(

            email=login_value

        ).first()



        if not user:



            user = User.query.filter_by(

                phone=login_value

            ).first()



        if not user:



            return render_template(

                "login.html",

                error="Account not found."

            )



        if not check_password_hash(

            user.password,

            password

        ):



            return render_template(

                "login.html",

                error="Incorrect password."

            )



        session["user_id"] = user.id

        session["user_name"] = user.name



        return redirect(

            url_for("home")

        )



    return render_template(

        "login.html"

    )





# =========================================================

# CUSTOMER DASHBOARD

# =========================================================



@app.route("/account")

def customer_dashboard():



    if not session.get("user_id"):



        return redirect(

            url_for("login")

        )



    user = User.query.get_or_404(

        session["user_id"]

    )



    orders = Order.query.filter_by(

        user_id=user.id

    ).order_by(

        Order.id.desc()

    ).all()



    return render_template(

        "customer_dashboard.html",

        user=user,

        orders=orders

    )



# =========================================================

# WALLET

# =========================================================



@app.route("/wallet")

def wallet():



    if not session.get("user_id"):

        return redirect(

            url_for("login")

        )



    user = User.query.get_or_404(

        session["user_id"]

    )



    transactions = CoinTransaction.query.filter_by(

        user_id=user.id

    ).order_by(

        CoinTransaction.id.desc()

    ).all()



    return render_template(

        "wallet.html",

        user=user,

        transactions=transactions

    )





# =========================================================

# LOGOUT

# =========================================================



@app.route("/logout")

def logout():



    session.pop(

        "user_id",

        None

    )



    session.pop(

        "user_name",

        None

    )



    return redirect(

        url_for("home")

    )





# =========================================================

# RECHARGE

# =========================================================



@app.route(

    "/recharge/<int:region_id>",

    methods=["GET", "POST"]

)

def recharge(region_id):



    if not session.get("user_id"):



        return redirect(

            url_for("login")

        )



    region = Region.query.get_or_404(

        region_id

    )



    packages = RegionPackage.query.filter_by(

        region_id=region.id,

        active=True

    ).order_by(

        RegionPackage.diamonds

    ).all()



    user = User.query.get_or_404(

        session["user_id"]

    )



    if request.method == "POST":



        package_id = request.form.get(

            "package_id"

        )



        payment_method = request.form.get(

            "payment_method",

            "razorpay"

        )



        mlbb_user_id = request.form.get(

            "user_id",

            ""

        ).strip()



        zone_id = request.form.get(

            "zone_id",

            ""

        ).strip()



        phone = request.form.get(

            "phone",

            ""

        ).strip()



        if not package_id:



            return render_template(

                "recharge.html",

                region=region,

                packages=packages,

                user=user,

                error="Please select a diamond package."

            )



        try:



            package = RegionPackage.query.get_or_404(

                int(package_id)

            )



        except Exception:



            return render_template(

                "recharge.html",

                region=region,

                packages=packages,

                user=user,

                error="Invalid package."

            )



        if package.region_id != region.id:



            return render_template(

                "recharge.html",

                region=region,

                packages=packages,

                user=user,

                error="Invalid package."

            )



        if not mlbb_user_id or not zone_id:



            return render_template(

                "recharge.html",

                region=region,

                packages=packages,

                user=user,

                error="Please enter your MLBB User ID and Zone ID."

            )



        if payment_method not in [

            "razorpay",

            "coins"

        ]:



            payment_method = "razorpay"



        # =================================================

        # COIN PAYMENT

        # =================================================



        if payment_method == "coins":



            required_coins = int(

                round(package.price)

            )



            db.session.refresh(user)



            if user.coins < required_coins:



                return render_template(

                    "recharge.html",

                    region=region,

                    packages=packages,

                    user=user,

                    error=(

                        f"Insufficient Chongzy Coins. "

                        f"You need {required_coins} Coins, "

                        f"but you only have {user.coins} Coins."

                    )

                )



            order_number = (

                "CZ"

                + str(uuid.uuid4())

                .replace("-", "")[:10]

                .upper()

            )



            order = Order(

                order_number=order_number,

                user_id=user.id,

                package_id=package.id,

                region_name=region.name,

                diamonds=package.diamonds,

                price=package.price,

                mlbb_user_id=mlbb_user_id,

                zone_id=zone_id,

                phone=phone,

                status="Paid",

                payment_method="coins",

                paid_at=datetime.utcnow()

            )



            user.coins -= required_coins



            transaction_number = (

                "CZC"

                + str(uuid.uuid4())

                .replace("-", "")[:10]

                .upper()

            )



            coin_transaction = CoinTransaction(

                transaction_number=transaction_number,

                user_id=user.id,

                coins=-required_coins,

                transaction_type="Diamond Recharge",

                amount=required_coins,

                status="Completed",

                paid_at=datetime.utcnow()

            )



            db.session.add(order)

            db.session.add(coin_transaction)



            try:



                db.session.commit()



            except Exception as e:



                db.session.rollback()



                print(

                    "Coin recharge error:",

                    e

                )



                return render_template(

                    "recharge.html",

                    region=region,

                    packages=packages,

                    user=user,

                    error="Unable to process coin payment."

                )



            return redirect(

                url_for(

                    "order_details",

                    order_id=order.id

                )

            )



        # =================================================

        # RAZORPAY PAYMENT

        # =================================================



        if not razorpay_client:



            return (

                "Razorpay is not configured."

            ), 500



        order_number = (

            "CZ"

            + str(uuid.uuid4())

            .replace("-", "")[:10]

            .upper()

        )



        order = Order(

            order_number=order_number,

            user_id=user.id,

            package_id=package.id,

            region_name=region.name,

            diamonds=package.diamonds,

            price=package.price,

            mlbb_user_id=mlbb_user_id,

            zone_id=zone_id,

            phone=phone,

            status="Pending",

            payment_method="razorpay"

        )



        db.session.add(order)

        db.session.commit()



        try:



            razorpay_order = razorpay_client.order.create({



                "amount": int(

                    round(order.price * 100)

                ),



                "currency": "INR",



                "receipt": order.order_number,



                "notes": {

                    "chongzystore_order":

                        order.order_number,



                    "mlbb_user_id":

                        order.mlbb_user_id,



                    "zone_id":

                        order.zone_id

                }

            })



            order.razorpay_order_id = (

                razorpay_order["id"]

            )



            db.session.commit()



        except Exception as e:



            print(

                "Razorpay error:",

                e

            )



            order.status = "Cancelled"

            db.session.commit()



            return (

                "Unable to create Razorpay payment."

            ), 500



        return redirect(

            url_for(

                "order_details",

                order_id=order.id

            )

        )



    return render_template(

        "recharge.html",

        region=region,

        packages=packages,

        user=user

    )





# =========================================================

# ORDER DETAILS

# =========================================================



@app.route(

    "/order/<int:order_id>"

)

def order_details(order_id):



    if not session.get("user_id"):



        return redirect(

            url_for("login")

        )



    order = Order.query.get_or_404(

        order_id

    )



    if order.user_id != session["user_id"]:



        return "Unauthorized", 403



    return render_template(

        "order_details.html",

        order=order,

        razorpay_key_id=RAZORPAY_KEY_ID

    )





# =========================================================
# RAZORPAY PAYMENT SUCCESS + ARCADEZY AUTO ORDER
# =========================================================

@app.route(
    "/payment/success",
    methods=["POST"]
)
def payment_success():

    if not session.get("user_id"):
        return redirect(
            url_for("login")
        )

    payment_id = request.form.get(
        "razorpay_payment_id"
    )

    razorpay_order_id = request.form.get(
        "razorpay_order_id"
    )

    signature = request.form.get(
        "razorpay_signature"
    )

    order_id = request.form.get(
        "order_id"
    )

    if not all([
        payment_id,
        razorpay_order_id,
        signature,
        order_id
    ]):
        return (
            "Invalid payment response.",
            400
        )

    try:
        order_id = int(order_id)

    except ValueError:
        return (
            "Invalid order ID.",
            400
        )

    order = Order.query.get_or_404(
        order_id
    )

    if order.user_id != session["user_id"]:
        return "Unauthorized", 403

    if not razorpay_client:
        return (
            "Razorpay is not configured.",
            500
        )

    # -----------------------------------------------------
    # CHECK RAZORPAY ORDER
    # -----------------------------------------------------

    if order.razorpay_order_id != razorpay_order_id:
        return (
            "Order verification failed.",
            400
        )

    # -----------------------------------------------------
    # VERIFY RAZORPAY SIGNATURE
    # -----------------------------------------------------

    try:

        razorpay_client.utility.verify_payment_signature({

            "razorpay_order_id":
                razorpay_order_id,

            "razorpay_payment_id":
                payment_id,

            "razorpay_signature":
                signature

        })

    except Exception as e:

        print(
            "Payment verification error:",
            e
        )

        return (
            "Payment verification failed.",
            400
        )

    # -----------------------------------------------------
    # VERIFY ACTUAL PAYMENT
    # -----------------------------------------------------

    try:

        payment = razorpay_client.payment.fetch(
            payment_id
        )

        expected_amount = int(
            round(order.price * 100)
        )

        actual_amount = int(
            payment.get(
                "amount",
                0
            )
        )

        if actual_amount != expected_amount:

            return (
                "Payment amount verification failed.",
                400
            )

        if payment.get("status") != "captured":

            return (
                "Payment has not been captured yet.",
                400
            )

    except Exception as e:

        print(
            "Payment fetch error:",
            e
        )

        return (
            "Unable to verify payment.",
            500
        )

    # -----------------------------------------------------
    # MARK LOCAL ORDER AS PAID
    # -----------------------------------------------------

    try:

        if not order.razorpay_payment_id:

            order.razorpay_payment_id = payment_id

        if order.status != "Paid":

            order.status = "Paid"

            order.paid_at = datetime.utcnow()

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "Local payment update error:",
            e
        )

        return (
            "Unable to process payment.",
            500
        )

    # -----------------------------------------------------
    # ARCADEZY AUTO ORDER
    # -----------------------------------------------------

    try:

        # Already sent to Arcadezy
        if order.arcadezy_order_id:

            return render_template(
                "recharge_success.html",
                order=order
            )

        # -------------------------------------------------
        # CHECK OFFER ID
        # -------------------------------------------------

        package = RegionPackage.query.get(
            order.package_id
        )

        if not package:

            order.arcadezy_error = (
                "Package not found."
            )

            db.session.commit()

            return render_template(
                "recharge_success.html",
                order=order
            )

        if not package.arcadezy_offer_id:

            order.arcadezy_error = (
                "Arcadezy offer ID is missing "
                "for this package."
            )

            db.session.commit()

            return render_template(
                "recharge_success.html",
                order=order
            )

        # -------------------------------------------------
        # CREATE IDEMPOTENCY KEY
        # -------------------------------------------------

        if not order.arcadezy_idempotency_key:

            order.arcadezy_idempotency_key = (
                "CZ-"
                + str(uuid.uuid4())
            )

            db.session.commit()

        # -------------------------------------------------
        # SEND ORDER TO ARCADEZY
        # -------------------------------------------------

        response = arcadezy_create_order(

            package.arcadezy_offer_id,

            order.mlbb_user_id,

            order.zone_id,

            order.arcadezy_idempotency_key

        )

        try:

            data = response.json()

        except Exception:

            data = {}

        print(
            "Arcadezy response:",
            data
        )

        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------

        if response.status_code in [200, 201]:

            arcadezy_order = data.get(
                "order",
                {}
            )

            arcadezy_order_id = (
                arcadezy_order.get("id")
                or data.get("order_id")
            )

            arcadezy_status = (
                arcadezy_order.get(
                    "status",
                    "paid"
                )
            )

            if arcadezy_order_id:

                order.arcadezy_order_id = (
                    str(arcadezy_order_id)
                )

                order.arcadezy_offer_id = (
                    str(package.arcadezy_offer_id)
                )

                order.arcadezy_status = (
                    str(arcadezy_status)
                )

                order.arcadezy_error = None

                # Arcadezy has accepted the order.
                order.status = "Processing"

                db.session.commit()

            else:

                order.arcadezy_error = (
                    "Arcadezy accepted the request "
                    "but returned no order ID."
                )

                db.session.commit()

            return render_template(
                "recharge_success.html",
                order=order
            )

        # -------------------------------------------------
        # ARCADEZY ERROR
        # -------------------------------------------------

        try:

            error_code = data.get(
                "code",
                ""
            )

            error_message = data.get(
                "error",
                "Arcadezy could not create the order."
            )

            if error_code:

                error_message = (
                    f"{error_code}: "
                    f"{error_message}"
                )

        except Exception:

            error_message = (
                "Arcadezy could not create the order."
            )

        order.arcadezy_error = (
            error_message
        )

        order.arcadezy_status = (
            "failed"
        )

        # Keep payment as Paid.
        # We do NOT pretend the customer was refunded.
        order.status = "Paid"

        db.session.commit()

        print(
            "Arcadezy order error:",
            error_message
        )

        return render_template(
            "recharge_success.html",
            order=order
        )

    except Exception as e:

        db.session.rollback()

        print(
            "Arcadezy order creation error:",
            e
        )

        try:

            order = Order.query.get(
                order_id
            )

            if order:

                order.arcadezy_error = (
                    str(e)
                )

                db.session.commit()

        except Exception:
            pass

        return render_template(
            "recharge_success.html",
            order=order
        )




# =========================================================

# ADMIN CONFIGURATION

# =========================================================



ADMIN_USERNAME = "Chongzy69"



ADMIN_PASSWORD = "Chongzy@123xd"





# =========================================================

# ADD COINS

# =========================================================



@app.route(

    "/add-coins",

    methods=["GET", "POST"]

)

def add_coins():



    if not session.get("user_id"):



        return redirect(

            url_for("login")

        )



    user = User.query.get_or_404(

        session["user_id"]

    )



    if request.method == "GET":



        return render_template(

            "add_coins.html",

            user=user

        )



    coins_text = request.form.get(

        "coins",

        ""

    ).strip()



    try:



        coins = int(coins_text)



    except ValueError:



        return render_template(

            "add_coins.html",

            user=user,

            error="Please enter a valid coin amount."

        )



    if coins < 1:



        return render_template(

            "add_coins.html",

            user=user,

            error="Please enter at least 1 coin."

        )



    amount = coins



    transaction_number = (

        "CZC"

        + str(uuid.uuid4())

        .replace("-", "")[:10]

        .upper()

    )



    transaction = CoinTransaction(

        transaction_number=transaction_number,

        user_id=user.id,

        coins=coins,

        transaction_type="Purchase",

        amount=amount,

        status="Pending"

    )



    db.session.add(transaction)

    db.session.commit()



    if not razorpay_client:



        transaction.status = "Failed"

        db.session.commit()



        return (

            "Razorpay is not configured."

        ), 500



    try:



        razorpay_order = razorpay_client.order.create({



            "amount": int(

                amount * 100

            ),



            "currency": "INR",



            "receipt": transaction_number,



            "notes": {



                "type":

                    "coin_purchase",



                "transaction_number":

                    transaction_number,



                "coins":

                    str(coins)

            }

        })



        transaction.razorpay_order_id = (

            razorpay_order["id"]

        )



        db.session.commit()



    except Exception as e:



        print(

            "Coin Razorpay Error:",

            e

        )



        transaction.status = "Failed"



        db.session.commit()



        return (

            "Unable to create payment."

        ), 500



    return redirect(

        url_for(

            "coin_payment",

            transaction_id=transaction.id

        )

    )





# =========================================================

# COIN PAYMENT

# =========================================================



@app.route(

    "/coins/payment/<int:transaction_id>"

)

def coin_payment(transaction_id):



    if not session.get("user_id"):



        return redirect(

            url_for("login")

        )



    transaction = CoinTransaction.query.get_or_404(

        transaction_id

    )



    if transaction.user_id != session["user_id"]:



        return "Unauthorized", 403



    user = User.query.get_or_404(

        session["user_id"]

    )



    if not transaction.razorpay_order_id:



        return (

            "Razorpay order was not created.",

            400

        )



    if not razorpay_client:



        return (

            "Razorpay is not configured.",

            500

        )



    return render_template(

        "coins_payment.html",

        transaction=transaction,

        user=user,

        razorpay_key_id=RAZORPAY_KEY_ID

    )





# =========================================================

# COIN PAYMENT SUCCESS

# =========================================================



@app.route(

    "/coins/payment/success",

    methods=["POST"]

)

def coin_payment_success():



    if not session.get("user_id"):



        return redirect(

            url_for("login")

        )



    transaction_id = request.form.get(

        "transaction_id"

    )



    payment_id = request.form.get(

        "razorpay_payment_id"

    )



    order_id = request.form.get(

        "razorpay_order_id"

    )



    signature = request.form.get(

        "razorpay_signature"

    )



    if not all([

        transaction_id,

        payment_id,

        order_id,

        signature

    ]):



        return (

            "Invalid payment response.",

            400

        )



    try:



        transaction_id = int(

            transaction_id

        )



    except ValueError:



        return (

            "Invalid transaction ID.",

            400

        )



    transaction = CoinTransaction.query.get_or_404(

        transaction_id

    )



    if transaction.user_id != session["user_id"]:



        return (

            "Unauthorized transaction.",

            403

        )



    # IMPORTANT:

    # Prevent duplicate coin crediting.

    if transaction.status == "Completed":



        user = User.query.get_or_404(

            transaction.user_id

        )



        return render_template(

            "coin_success.html",

            transaction=transaction,

            user=user

        )



    if not razorpay_client:



        return (

            "Razorpay is not configured.",

            500

        )



    if transaction.razorpay_order_id != order_id:



        return (

            "Invalid Razorpay order.",

            400

        )



    # -----------------------------------------------------

    # VERIFY SIGNATURE

    # -----------------------------------------------------



    try:



        razorpay_client.utility.verify_payment_signature({



            "razorpay_order_id":

                order_id,



            "razorpay_payment_id":

                payment_id,



            "razorpay_signature":

                signature



        })



    except Exception as e:



        print(

            "Coin payment signature error:",

            e

        )



        transaction.status = "Failed"



        db.session.commit()



        return (

            "Payment verification failed. "

            "Your coins were NOT added."

        ), 400



    # -----------------------------------------------------

    # VERIFY ACTUAL PAYMENT

    # -----------------------------------------------------



    try:



        payment = razorpay_client.payment.fetch(

            payment_id

        )



        actual_amount = int(

            payment.get(

                "amount",

                0

            )

        )



        expected_amount = int(

            round(

                transaction.amount * 100

            )

        )



        if actual_amount != expected_amount:



            transaction.status = "Failed"



            db.session.commit()



            return (

                "Payment amount verification failed.",

                400

            )



        if payment.get(

            "status"

        ) != "captured":



            transaction.status = "Failed"



            db.session.commit()



            return (

                "Payment has not been captured yet.",

                400

            )



    except Exception as e:



        print(

            "Coin payment fetch error:",

            e

        )



        return (

            "Unable to verify payment status.",

            400

        )



    # -----------------------------------------------------

    # ADD COINS

    # -----------------------------------------------------



    try:



        user = User.query.get_or_404(

            transaction.user_id

        )



        user.coins += transaction.coins



        transaction.razorpay_payment_id = (

            payment_id

        )



        transaction.status = "Completed"



        transaction.paid_at = datetime.utcnow()



        db.session.commit()



    except Exception as e:



        db.session.rollback()



        print(

            "Coin credit error:",

            e

        )



        return (

            "Payment was received, "

            "but the server could not process "

            "the transaction. Please contact support."

        ), 500



    return render_template(

        "coin_success.html",

        transaction=transaction,

        user=user

    )





# =========================================================

# ADMIN LOGIN

# =========================================================



@app.route(

    "/admin",

    methods=["GET", "POST"]

)

def admin_login():



    if request.method == "POST":



        username = request.form.get(

            "username",

            ""

        ).strip()



        password = request.form.get(

            "password",

            ""

        )



        if (

            username == ADMIN_USERNAME

            and password == ADMIN_PASSWORD

        ):



            session["admin_logged_in"] = True



            return redirect(

                url_for("admin_dashboard")

            )



        return render_template(

            "admin_login.html",

            error="Incorrect username or password."

        )



    return render_template(

        "admin_login.html"

    )





# =========================================================

# ADMIN DASHBOARD

# =========================================================

@app.route("/admin/remove-duplicate-adventure")
def remove_duplicate_adventure():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    # Find all Adventure regions
    adventure_regions = Region.query.filter(
        db.or_(
            Region.name.ilike("Adventure"),
            Region.name.ilike("%Adventure%")
        )
    ).order_by(
        Region.id.asc()
    ).all()

    if len(adventure_regions) <= 1:
        return """
        <h2>✅ No duplicate Adventure found.</h2>
        <p>There is already only one Adventure region.</p>
        <a href="/">Go Home</a>
        """

    # Keep the first Adventure region
    keep_region = adventure_regions[0]

    removed_regions = 0
    removed_duplicate_packages = 0

    # Process every extra Adventure region
    for duplicate_region in adventure_regions[1:]:

        packages = RegionPackage.query.filter_by(
            region_id=duplicate_region.id
        ).all()

        for package in packages:

            # Check whether this exact Arcadezy offer
            # already exists in the region we are keeping
            existing = None

            if package.arcadezy_offer_id:
                existing = RegionPackage.query.filter_by(
                    region_id=keep_region.id,
                    arcadezy_offer_id=package.arcadezy_offer_id
                ).first()

            if existing:

                # Already have this package
                db.session.delete(package)
                removed_duplicate_packages += 1

            else:

                # Move package to the Adventure region we keep
                package.region_id = keep_region.id

        # Now it is safe to remove the duplicate region
        db.session.delete(duplicate_region)
        removed_regions += 1

    db.session.commit()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Adventure Cleanup</title>
        <style>
            body {{
                background:#050505;
                color:white;
                font-family:Arial;
                text-align:center;
                padding:60px;
            }}
            .box {{
                max-width:600px;
                margin:auto;
                background:#151515;
                padding:40px;
                border-radius:20px;
                border:1px solid #333;
            }}
            a {{
                display:inline-block;
                margin-top:25px;
                padding:14px 25px;
                background:#ffd000;
                color:#000;
                text-decoration:none;
                border-radius:10px;
                font-weight:bold;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>✅ Adventure Fixed</h1>

            <h2>Kept: 1 Adventure</h2>

            <p>
                Removed duplicate regions:
                <b>{removed_regions}</b>
            </p>

            <p>
                Removed duplicate packages:
                <b>{removed_duplicate_packages}</b>
            </p>

            <a href="/">GO TO HOMEPAGE</a>
        </div>
    </body>
    </html>
    """

@app.route(

    "/admin/dashboard"

)

def admin_dashboard():



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    regions = Region.query.order_by(

        Region.id.desc()

    ).all()



    packages = RegionPackage.query.order_by(

        RegionPackage.id.desc()

    ).all()



    accounts = Account.query.order_by(

        Account.id.desc()

    ).all()



    orders = Order.query.order_by(

        Order.id.desc()

    ).all()



    users = User.query.order_by(

        User.id.desc()

    ).all()



    inquiries = AccountInquiry.query.order_by(

        AccountInquiry.id.desc()

    ).all()



    coin_transactions = CoinTransaction.query.order_by(

        CoinTransaction.id.desc()

    ).all()



    return render_template(

        "admin_dashboard.html",

        regions=regions,

        packages=packages,

        accounts=accounts,

        orders=orders,

        users=users,

        inquiries=inquiries,

        coin_transactions=coin_transactions

    )





# =========================================================

# ADMIN - MODIFY USER COINS

# =========================================================



@app.route(

    "/admin/user-coins/<int:user_id>",

    methods=["POST"]

)

def admin_user_coins(user_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    user = User.query.get_or_404(

        user_id

    )



    action = request.form.get(

        "action",

        "add"

    )



    try:



        amount = int(

            request.form.get(

                "amount",

                request.form.get(

                    "coins",

                    0

                )

            )

        )



    except ValueError:



        return (

            "Invalid coin amount.",

            400

        )



    if amount < 0:



        return (

            "Coin amount cannot be negative.",

            400

        )



    if action == "add":



        user.coins += amount



        transaction_type = "Admin Added"



        transaction_coins = amount



    elif action == "remove":



        if amount > user.coins:



            return (

                "User does not have enough coins.",

                400

            )



        user.coins -= amount



        transaction_type = "Admin Removed"



        transaction_coins = -amount



    elif action == "set":



        difference = (

            amount - user.coins

        )



        user.coins = amount



        transaction_type = "Admin Balance Set"



        transaction_coins = difference



    else:



        return (

            "Invalid action.",

            400

        )



    transaction_number = (

        "ADM"

        + str(uuid.uuid4())

        .replace("-", "")[:10]

        .upper()

    )



    transaction = CoinTransaction(

        transaction_number=transaction_number,

        user_id=user.id,

        coins=transaction_coins,

        amount=0,

        transaction_type=transaction_type,

        status="Completed",

        paid_at=datetime.utcnow()

    )



    db.session.add(transaction)



    db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )


# =========================================================
# ARCADEZY - TEST MLBB PRODUCTS
# =========================================================

@app.route("/admin/arcadezy-products")
def arcadezy_products():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    try:

        response = arcadezy_get_offers()

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code != 200:

            return {
                "success": False,
                "status_code": response.status_code,
                "message": data.get(
                    "error",
                    "Arcadezy could not return the products."
                ),
                "response": data
            }, response.status_code

        return {
            "success": True,
            "message": "Arcadezy products loaded successfully.",
            "products": data
        }

    except Exception as e:

        print(
            "Arcadezy product error:",
            str(e)
        )

        return {
            "success": False,
            "message": "Could not connect to Arcadezy.",
            "error": str(e)
        }, 500

    # =========================================================
# ADMIN - ARCADEZY PRODUCT MANAGER
# =========================================================

@app.route("/admin/products")
def admin_products():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    regions = Region.query.order_by(
        Region.name
    ).all()

    packages = RegionPackage.query.order_by(
        RegionPackage.id.desc()
    ).all()

    return render_template(
        "admin_products.html",
        regions=regions,
        packages=packages
    )


# =========================================================
# ADMIN - SAVE PRODUCT
# =========================================================

@app.route(
    "/admin/products/save/<int:package_id>",
    methods=["POST"]
)
def admin_save_product(package_id):

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    package = RegionPackage.query.get_or_404(
        package_id
    )

    package.package_name = request.form.get(
        "package_name",
        ""
    ).strip()

    diamonds = request.form.get(
        "diamonds",
        ""
    ).strip()

    price = request.form.get(
        "price",
        ""
    ).strip()

    arcadezy_offer_id = request.form.get(
        "arcadezy_offer_id",
        ""
    ).strip()

    active = request.form.get(
        "active"
    )

    try:

        if diamonds:
            package.diamonds = int(
                diamonds
            )
        else:
            package.diamonds = None

        package.price = float(
            price or 0
        )

    except ValueError:

        return (
            "Invalid diamonds or price.",
            400
        )

    package.arcadezy_offer_id = (
        arcadezy_offer_id
        or None
    )

    package.active = (
        active == "1"
    )

    db.session.commit()

    return redirect(
        url_for("admin_products")
    )


# =========================================================

# ADMIN - ADD REGION

# =========================================================



@app.route(

    "/admin/add-region",

    methods=["POST"]

)

def add_region():



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    name = request.form.get(

        "name",

        ""

    ).strip()



    code = request.form.get(

        "code",

        ""

    ).strip()



    if name and code:



        existing = Region.query.filter_by(

            name=name

        ).first()



        if not existing:



            region = Region(

                name=name,

                code=code

            )



            db.session.add(region)



            db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - DELETE REGION

# =========================================================



@app.route(

    "/admin/delete-region/<int:region_id>"

)

def delete_region(region_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    region = Region.query.get_or_404(

        region_id

    )



    db.session.delete(region)



    db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - ADD REGION PACKAGE

# =========================================================



@app.route(

    "/admin/add-region-package",

    methods=["POST"]

)

def add_region_package():



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    region_id = request.form.get(

        "region_id"

    )



    diamonds = request.form.get(

        "diamonds"

    )



    price = request.form.get(

        "price"

    )



    if region_id and diamonds and price:



        try:



            package = RegionPackage(

                region_id=int(region_id),

                diamonds=int(diamonds),

                price=float(price),

                active=True

            )



            db.session.add(package)



            db.session.commit()



        except ValueError:



            return (

                "Invalid package values.",

                400

            )



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================
# ADMIN - DELETE PACKAGE
# =========================================================

@app.route(
    "/admin/delete-region-package/<int:package_id>"
)
def delete_region_package(package_id):

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    package = RegionPackage.query.get_or_404(
        package_id
    )

    # Remember the page/filter the admin came from
    region_id = request.args.get(
        "region_id",
        type=int
    )

    search = request.args.get(
        "search",
        "",
        type=str
    ).strip()

    db.session.delete(package)
    db.session.commit()

    # Stay on Manage Packages
    return redirect(
        url_for(
            "manage_packages",
            region_id=region_id,
            search=search
        )
    )

# =========================================================
# ADMIN - REMOVE INVALID 0 DIAMOND PACKAGES
# =========================================================

@app.route("/admin/cleanup-zero-packages")
def cleanup_zero_packages():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    packages = RegionPackage.query.filter(
        RegionPackage.diamonds <= 0
    ).all()

    removed_count = len(packages)

    for package in packages:
        db.session.delete(package)

    db.session.commit()

    return f"""
    <html>
    <head>
        <title>Cleanup Complete</title>
        <style>
            body {{
                background: #0b1020;
                color: white;
                font-family: Arial, sans-serif;
                text-align: center;
                padding-top: 100px;
            }}

            .box {{
                max-width: 600px;
                margin: auto;
                padding: 40px;
                background: #151c32;
                border-radius: 20px;
            }}

            a {{
                display: inline-block;
                margin-top: 25px;
                padding: 14px 25px;
                background: #00c853;
                color: white;
                text-decoration: none;
                border-radius: 10px;
                font-weight: bold;
            }}
        </style>
    </head>

    <body>

        <div class="box">

            <h1>✅ Cleanup Complete</h1>

            <h2>{removed_count} packages removed</h2>

            <p>
                All packages with 0 or negative diamonds
                have been removed.
            </p>

            <a href="/admin/manage-packages">
                ← Back to Manage Packages
            </a>

        </div>

    </body>
    </html>
    """

# =========================================================
# ADMIN - MANAGE ALL PACKAGES
# =========================================================

@app.route("/admin/manage-packages")
def manage_packages():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    region_id = request.args.get(
        "region_id",
        type=int
    )

    search = request.args.get(
        "search",
        "",
        type=str
    ).strip()

    regions = Region.query.order_by(
        Region.name.asc()
    ).all()

    query = RegionPackage.query

    if region_id:
        query = query.filter_by(
            region_id=region_id
        )

    if search:
        try:
            search_number = int(search)

            query = query.filter(
                RegionPackage.diamonds == search_number
            )

        except ValueError:
            query = query.filter(
                RegionPackage.package_name.ilike(
                    f"%{search}%"
                )
            )

    packages = query.order_by(
        RegionPackage.diamonds.asc()
    ).all()

    return render_template(
        "manage_packages.html",
        regions=regions,
        packages=packages,
        selected_region_id=region_id,
        search=search
    )


# =========================================================
# ADMIN - UPDATE PACKAGE
# =========================================================

@app.route(
    "/admin/update-package/<int:package_id>",
    methods=["POST"]
)
def update_package(package_id):

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    package = RegionPackage.query.get_or_404(
        package_id
    )

    diamonds = request.form.get(
        "diamonds",
        ""
    ).strip()

    price = request.form.get(
        "price",
        ""
    ).strip()

    active = request.form.get(
        "active"
    )

    try:

        package.diamonds = int(
            diamonds
        )

        package.price = float(
            price
        )

    except ValueError:

        return (
            "Invalid diamonds or price.",
            400
        )

    package.active = (
        active == "1"
    )

    db.session.commit()

    return redirect(
        url_for(
            "manage_packages",
            region_id=package.region_id
        )
    )

# =========================================================
# ADMIN - AUTO PRICE ALL ARCADEZY PACKAGES
# =========================================================

@app.route(
    "/admin/auto-price-packages",
    methods=["POST"]
)
def auto_price_packages():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    packages = RegionPackage.query.all()

    updated = 0

    for package in packages:

        # Get Arcadezy supplier price
        supplier_price = getattr(
            package,
            "arcadezy_price_usd",
            None
        )

        if supplier_price is None:
            continue

        try:
            supplier_price = float(
                supplier_price
            )
        except (
            TypeError,
            ValueError
        ):
            continue

        if supplier_price <= 0:
            continue

        # Convert USD supplier price
        # to a simple INR retail price.
        #
        # Starting conversion:
        # $1 = approximately ₹100
        #
        # Then add a small margin.

        base_price = supplier_price * 100

        # Add ₹5 margin
        selling_price = base_price + 5

        # Round UP to nearest ₹5
        selling_price = (
            int(
                (selling_price + 4) // 5
            ) * 5
        )

        package.price = float(
            selling_price
        )

        # Keep inactive until we verify
        # the prices.
        package.active = False

        updated += 1

    db.session.commit()

    return f"""
    <!DOCTYPE html>

    <html>

    <head>

        <title>
            Pricing Complete
        </title>

        <style>

            body {{
                background:#080d1c;
                color:white;
                font-family:Arial,sans-serif;
                text-align:center;
                padding-top:100px;
            }}

            .box {{
                max-width:650px;
                margin:auto;
                background:#121a30;
                padding:45px;
                border-radius:20px;
            }}

            h1 {{
                color:#00d9ff;
            }}

            .number {{
                font-size:42px;
                color:#00ff99;
                font-weight:bold;
            }}

            a {{
                display:inline-block;
                margin-top:30px;
                padding:15px 25px;
                background:#00bfff;
                color:white;
                text-decoration:none;
                border-radius:10px;
                font-weight:bold;
            }}

        </style>

    </head>

    <body>

        <div class="box">

            <h1>
                ✅ Automatic Pricing Complete
            </h1>

            <p>
                Packages priced:
            </p>

            <div class="number">
                {updated}
            </div>

            <p>
                All packages are still
                <strong>INACTIVE</strong>.
            </p>

            <p>
                We will check the prices before
                activating them.
            </p>

            <a href="/admin/manage-packages">
                📦 Manage Packages
            </a>

        </div>

    </body>

    </html>
    """

# =========================================================
# ACTIVATE ALL VALID ARCADEZY PACKAGES
# =========================================================

@app.route(
    "/admin/activate-all-packages",
    methods=["POST"]
)
def activate_all_packages():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    packages = RegionPackage.query.all()

    activated = 0
    skipped = 0

    for package in packages:

        # Only activate products that have:
        # 1. Valid diamonds
        # 2. A selling price
        # 3. Arcadezy offer ID
        # 4. Arcadezy supplier price

        if (
            package.diamonds
            and package.diamonds > 0
            and package.price
            and package.price > 0
            and package.arcadezy_offer_id
            and package.arcadezy_price_usd
            and package.arcadezy_price_usd > 0
        ):

            package.active = True

            activated += 1

        else:

            package.active = False

            skipped += 1

    db.session.commit()

    return f"""
    <html>
    <head>
        <title>Packages Activated</title>

        <style>
            body {{
                background:#080d18;
                color:white;
                font-family:Arial;
                text-align:center;
                padding:80px;
            }}

            .box {{
                max-width:600px;
                margin:auto;
                background:#111827;
                padding:40px;
                border-radius:20px;
                box-shadow:0 20px 50px rgba(0,0,0,.5);
            }}

            h1 {{
                color:#00e676;
            }}

            .number {{
                font-size:45px;
                font-weight:bold;
                margin:20px;
            }}

            a {{
                display:inline-block;
                margin-top:25px;
                padding:14px 25px;
                background:#00c853;
                color:white;
                text-decoration:none;
                border-radius:10px;
            }}
        </style>
    </head>

    <body>

        <div class="box">

            <h1>✓ Packages Activated</h1>

            <div class="number">
                {activated}
            </div>

            <p>
                valid Arcadezy packages are now active.
            </p>

            <p>
                {skipped} invalid/incomplete packages were kept inactive.
            </p>

            <a href="/admin/manage-packages">
                Back to Manage Packages
            </a>

        </div>

    </body>
    </html>
    """

# =========================================================

# ADMIN - CHANGE ORDER STATUS

# =========================================================



@app.route(

    "/admin/order-status/<int:order_id>",

    methods=["POST"]

)

def change_order_status(order_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    order = Order.query.get_or_404(

        order_id

    )



    status = request.form.get(

        "status"

    )



    allowed_statuses = [

        "Pending",

        "Paid",

        "Processing",

        "Completed",

        "Cancelled"

    ]



    if status in allowed_statuses:



        order.status = status



        db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - CHANGE INQUIRY STATUS

# =========================================================



@app.route(

    "/admin/inquiry-status/<int:inquiry_id>",

    methods=["POST"]

)

def change_inquiry_status(inquiry_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    inquiry = AccountInquiry.query.get_or_404(

        inquiry_id

    )



    status = request.form.get(

        "status"

    )



    allowed_statuses = [

        "Pending",

        "Contacted",

        "Sold",

        "Cancelled"

    ]



    if status in allowed_statuses:



        inquiry.status = status



        db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - ADD ACCOUNT

# =========================================================



@app.route(

    "/admin/add-account",

    methods=["POST"]

)

def add_account():



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    title = request.form.get(

        "title",

        ""

    ).strip()



    price = request.form.get(

        "price",

        "0"

    )



    usd_price = request.form.get(

        "usd_price",

        "0"

    )



    rank = request.form.get(

        "rank",

        ""

    ).strip()



    level = request.form.get(

        "level",

        ""

    ).strip()



    skins = request.form.get(

        "skins",

        ""

    ).strip()



    heroes = request.form.get(

        "heroes",

        ""

    ).strip()



    description = request.form.get(

        "description",

        ""

    ).strip()



    image_file = request.files.get(

        "image"

    )



    image_filename = ""



    if image_file and image_file.filename:



        filename = secure_filename(

            image_file.filename

        )



        extension = os.path.splitext(

            filename

        )[1]



        unique_filename = (

            str(uuid.uuid4())

            + extension

        )



        image_file.save(

            os.path.join(

                app.config["UPLOAD_FOLDER"],

                unique_filename

            )

        )



        image_filename = unique_filename



    try:



        account = Account(

            title=title,

            price=float(price or 0),

            usd_price=float(

                usd_price or 0

            ),

            rank=rank,

            level=level,

            skins=skins,

            heroes=heroes,

            description=description,

            image=image_filename,

            status="Available"

        )



        db.session.add(account)



        db.session.commit()



    except ValueError:



        return (

            "Invalid account price.",

            400

        )



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - EDIT ACCOUNT

# =========================================================



@app.route(

    "/admin/edit-account/<int:account_id>",

    methods=["GET", "POST"]

)

def edit_account(account_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    account = Account.query.get_or_404(

        account_id

    )



    if request.method == "POST":



        account.title = request.form.get(

            "title",

            ""

        ).strip()



        try:



            account.price = float(

                request.form.get(

                    "price",

                    0

                ) or 0

            )



            account.usd_price = float(

                request.form.get(

                    "usd_price",

                    0

                ) or 0

            )



        except ValueError:



            return (

                "Invalid price.",

                400

            )



        account.rank = request.form.get(

            "rank",

            ""

        ).strip()



        account.level = request.form.get(

            "level",

            ""

        ).strip()



        account.skins = request.form.get(

            "skins",

            ""

        ).strip()



        account.heroes = request.form.get(

            "heroes",

            ""

        ).strip()



        account.description = request.form.get(

            "description",

            ""

        ).strip()



        image_file = request.files.get(

            "image"

        )



        if image_file and image_file.filename:



            filename = secure_filename(

                image_file.filename

            )



            extension = os.path.splitext(

                filename

            )[1]



            unique_filename = (

                str(uuid.uuid4())

                + extension

            )



            image_file.save(

                os.path.join(

                    app.config["UPLOAD_FOLDER"],

                    unique_filename

                )

            )



            account.image = unique_filename



        db.session.commit()



        return redirect(

            url_for(

                "admin_dashboard"

            )

        )



    return render_template(

        "edit_account.html",

        account=account

    )





# =========================================================

# ADMIN - RESTORE ACCOUNT

# =========================================================



@app.route(

    "/admin/restore-account/<int:account_id>"

)

def restore_account(account_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    account = Account.query.get_or_404(

        account_id

    )



    account.status = "Available"



    db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - MARK ACCOUNT SOLD

# =========================================================



@app.route(

    "/admin/sold/<int:account_id>"

)

def mark_sold(account_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    account = Account.query.get_or_404(

        account_id

    )



    account.status = "Sold"



    db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )





# =========================================================

# ADMIN - DELETE ACCOUNT

# =========================================================



@app.route(

    "/admin/delete-account/<int:account_id>"

)

def delete_account(account_id):



    if not session.get(

        "admin_logged_in"

    ):



        return redirect(

            url_for("admin_login")

        )



    account = Account.query.get_or_404(

        account_id

    )



    db.session.delete(account)



    db.session.commit()



    return redirect(

        url_for("admin_dashboard")

    )


# =========================================================
# ADMIN - CLEAN DEMO DATA
# =========================================================

@app.route(
    "/admin/cleanup-demo-data",
    methods=["POST"]
)
def cleanup_demo_data():

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    try:

        # -------------------------------------------------
        # DELETE ALL MLBB ACCOUNTS FOR SALE
        # -------------------------------------------------

        Account.query.delete(
            synchronize_session=False
        )

        # -------------------------------------------------
        # DELETE ALL ORDERS / HISTORY
        # -------------------------------------------------

        Order.query.delete(
            synchronize_session=False
        )

        # -------------------------------------------------
        # DELETE ACCOUNT INQUIRIES
        # -------------------------------------------------

        try:
            AccountInquiry.query.delete(
                synchronize_session=False
            )
        except Exception:
            pass

        db.session.commit()

        # -------------------------------------------------
        # DELETE UPLOADED ACCOUNT IMAGES
        # -------------------------------------------------

        upload_folder = app.config["UPLOAD_FOLDER"]

        if os.path.exists(upload_folder):

            for filename in os.listdir(upload_folder):

                file_path = os.path.join(
                    upload_folder,
                    filename
                )

                if os.path.isfile(file_path):

                    try:
                        os.remove(file_path)

                    except Exception as e:
                        print(
                            "Could not delete:",
                            file_path,
                            e
                        )

        return redirect(
            url_for("admin_dashboard")
        )

    except Exception as e:

        db.session.rollback()

        print(
            "Demo cleanup error:",
            str(e)
        )

        return (
            "Cleanup failed: " + str(e),
            500
        )


# =========================================================

# ADMIN LOGOUT

# =========================================================



@app.route(

    "/admin/logout"

)

def admin_logout():



    session.pop(

        "admin_logged_in",

        None

    )



    return redirect(

        url_for("admin_login")

    )





# =========================================================

# SITEMAP

# =========================================================



@app.route(

    "/sitemap.xml"

)

def sitemap():



    pages = [

        "https://chongzystore.in/",

        "https://chongzystore.in/terms",

        "https://chongzystore.in/privacy",

        "https://chongzystore.in/refund",

        "https://chongzystore.in/faq",

        "https://chongzystore.in/login",

        "https://chongzystore.in/register"

    ]



    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>

<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

"""



    for page in pages:



        sitemap_xml += f"""    <url>

        <loc>{page}</loc>

    </url>

"""



    sitemap_xml += """</urlset>"""



    return Response(

        sitemap_xml,

        mimetype="application/xml"

    )





# =========================================================

# ROBOTS.TXT

# =========================================================



@app.route(

    "/robots.txt"

)

def robots():



    return Response(

        """User-agent: *

Allow: /



Sitemap: https://chongzystore.in/sitemap.xml

""",

        mimetype="text/plain"

    )





# =========================================================

# RUN

# =========================================================



if __name__ == "__main__":



    app.run(

        debug=True

    )