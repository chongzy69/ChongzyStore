from flask import Flask, render_template, request, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import razorpay
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

RAZORPAY_KEY_ID = os.environ.get(
    "RAZORPAY_KEY_ID"
)

RAZORPAY_KEY_SECRET = os.environ.get(
    "RAZORPAY_KEY_SECRET"
)


razorpay_client = None


if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:

    razorpay_client = razorpay.Client(
        auth=(
            RAZORPAY_KEY_ID,
            RAZORPAY_KEY_SECRET
        )
    )


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
    # =========================================================
# MLBB ACCOUNT PURCHASE INQUIRY
# =========================================================

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

    diamonds = db.Column(
        db.Integer,
        nullable=False
    )

    price = db.Column(
        db.Float,
        nullable=False
    )

    active = db.Column(
        db.Boolean,
        default=True
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
    # ADD USD PRICE TO OLD ACCOUNT TABLE
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

    if (
        account_columns
        and "usd_price" not in account_column_names
    ):

        print(
            "Adding usd_price column to existing account table..."
        )

        db.session.execute(
            db.text(
                "ALTER TABLE account "
                "ADD COLUMN usd_price FLOAT DEFAULT 0"
            )
        )

        db.session.commit()

        print(
            "usd_price column added successfully."
        )


    # -----------------------------------------------------
    # ADD RAZORPAY COLUMNS TO OLD ORDER TABLE
    # -----------------------------------------------------

    order_columns = db.session.execute(
        db.text(
            'PRAGMA table_info("order")'
        )
    ).fetchall()

    order_column_names = [
        row[1]
        for row in order_columns
    ]

    if order_columns:

        if (
            "razorpay_order_id"
            not in order_column_names
        ):

            db.session.execute(
                db.text(
                    'ALTER TABLE "order" '
                    'ADD COLUMN razorpay_order_id VARCHAR(100)'
                )
            )


        if (
            "razorpay_payment_id"
            not in order_column_names
        ):

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


        db.session.commit()


    print(
        "Database setup complete."
    )


# =========================================================
# CUSTOMER HOME
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

@app.route("/")
def home():

    regions = Region.query.order_by(
        Region.name
    ).all()

    accounts = Account.query.filter_by(
        status="Available"
    ).all()

    return render_template(
        "index.html",
        regions=regions,
        accounts=accounts
    )
# =========================================================
# MLBB ACCOUNT DETAILS
# =========================================================

@app.route("/account-details/<int:account_id>")
def account_details(account_id):

    account = Account.query.get_or_404(account_id)

    return render_template(
        "account_details.html",
        account=account
    )
# =========================================================
# MLBB ACCOUNT PURCHASE INQUIRY
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
            )
        )

        db.session.add(
            new_user
        )

        db.session.commit()


        session["user_id"] = new_user.id

        session["user_name"] = new_user.name


        return redirect(
            url_for(
                "customer_dashboard"
            )
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
            url_for(
                "customer_dashboard"
            )
        )


    return render_template(
        "login.html"
    )


# =========================================================
# CUSTOMER ACCOUNT
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


    if request.method == "POST":

        package_id = request.form.get(
            "package_id"
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
                error="Please select a diamond package."
            )


        package = RegionPackage.query.get_or_404(
            int(package_id)
        )


        if package.region_id != region.id:

            return render_template(
                "recharge.html",
                region=region,
                packages=packages,
                error="Invalid package."
            )


        if not mlbb_user_id or not zone_id:

            return render_template(
                "recharge.html",
                region=region,
                packages=packages,
                error=(
                    "Please enter your MLBB User ID "
                    "and Zone ID."
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

            user_id=session["user_id"],

            package_id=package.id,

            region_name=region.name,

            diamonds=package.diamonds,

            price=package.price,

            mlbb_user_id=mlbb_user_id,

            zone_id=zone_id,

            phone=phone,

            status="Pending"
        )


        db.session.add(order)

        db.session.commit()


        # -------------------------------------------------
        # CREATE RAZORPAY ORDER
        # -------------------------------------------------

        if razorpay_client:

            try:

                razorpay_order = (
                    razorpay_client.order.create(
                        {
                            "amount": int(
                                round(
                                    order.price * 100
                                )
                            ),

                            "currency": "INR",

                            "receipt":
                                order.order_number,

                            "notes": {

                                "chongzystore_order":
                                    order.order_number,

                                "mlbb_user_id":
                                    order.mlbb_user_id,

                                "zone_id":
                                    order.zone_id
                            }
                        }
                    )
                )


                order.razorpay_order_id = (
                    razorpay_order["id"]
                )


                db.session.commit()


            except Exception as e:

                print(
                    "Razorpay error:",
                    e
                )


        return redirect(
            url_for(
                "order_details",
                order_id=order.id
            )
        )


    return render_template(
        "recharge.html",
        region=region,
        packages=packages
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
# RAZORPAY PAYMENT VERIFICATION
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


    if (
        not payment_id
        or not razorpay_order_id
        or not signature
        or not order_id
    ):

        return (
            "Invalid payment response.",
            400
        )


    try:

        order = Order.query.get_or_404(
            int(order_id)
        )

    except ValueError:

        return (
            "Invalid order ID.",
            400
        )


    if order.user_id != session["user_id"]:

        return "Unauthorized", 403


    if not razorpay_client:

        return (
            "Razorpay is not configured.",
            500
        )


    try:

        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id":
                    razorpay_order_id,

                "razorpay_payment_id":
                    payment_id,

                "razorpay_signature":
                    signature
            }
        )


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
    # VERIFY RAZORPAY ORDER
    # -----------------------------------------------------

    if (
        order.razorpay_order_id
        != razorpay_order_id
    ):

        return (
            "Order verification failed.",
            400
        )


    # -----------------------------------------------------
    # MARK ORDER AS PAID
    # -----------------------------------------------------

    order.razorpay_payment_id = payment_id

    order.status = "Paid"

    order.paid_at = datetime.utcnow()


    db.session.commit()


    # -----------------------------------------------------
    # PAYMENT SUCCESS PAGE
    # -----------------------------------------------------

    return render_template(
        "recharge_success.html",
        order=order
    )


# =========================================================
# ADMIN
# =========================================================

ADMIN_USERNAME = "Chongzy69"

ADMIN_PASSWORD = "Chongzy@123xd"


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
            "username"
        )

        password = request.form.get(
            "password"
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

@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    regions = Region.query.order_by(
        Region.id.desc()
    ).all()

    packages = RegionPackage.query.order_by(
        RegionPackage.id.desc()
    ).all()

    accounts = Account.query.all()

    orders = Order.query.order_by(
        Order.id.desc()
    ).all()

    users = User.query.order_by(
        User.id.desc()
    ).all()

    # MLBB ACCOUNT PURCHASE INQUIRIES
    inquiries = AccountInquiry.query.order_by(
        AccountInquiry.id.desc()
    ).all()

    return render_template(
        "admin_dashboard.html",
        regions=regions,
        packages=packages,
        accounts=accounts,
        orders=orders,
        users=users,
        inquiries=inquiries
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

        package = RegionPackage(

            region_id=int(region_id),

            diamonds=int(diamonds),

            price=float(price)

        )


        db.session.add(package)

        db.session.commit()


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

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for("admin_login")
        )


    package = RegionPackage.query.get_or_404(
        package_id
    )


    db.session.delete(package)

    db.session.commit()


    return redirect(
        url_for("admin_dashboard")
    )


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
# ADMIN - CHANGE ACCOUNT INQUIRY STATUS
# =========================================================

@app.route(
    "/admin/inquiry-status/<int:inquiry_id>",
    methods=["POST"]
)
def change_inquiry_status(inquiry_id):

    if not session.get("admin_logged_in"):

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
        "title"
    )

    price = request.form.get(
        "price"
    )

    usd_price = request.form.get(
        "usd_price"
    )

    rank = request.form.get(
        "rank"
    )

    level = request.form.get(
        "level"
    )

    skins = request.form.get(
        "skins"
    )

    heroes = request.form.get(
        "heroes"
    )

    description = request.form.get(
        "description"
    )


    image_file = request.files.get(
        "image"
    )


    image_filename = ""


    if (
        image_file
        and image_file.filename
    ):

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


    account = Account(

        title=title,

        price=float(
            price or 0
        ),

        usd_price=float(
            usd_price or 0
        ),

        rank=rank,

        level=level,

        skins=skins,

        heroes=heroes,

        description=description,

        image=image_filename
    )


    db.session.add(account)

    db.session.commit()


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

    if not session.get("admin_logged_in"):
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


        # ==========================================
        # NEW IMAGE
        # ==========================================

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

    if not session.get("admin_logged_in"):
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
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
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

@app.route("/sitemap.xml")
def sitemap():

    pages = [
        url_for("home", _external=True),
        url_for("terms", _external=True),
        url_for("privacy", _external=True),
        url_for("refund", _external=True),
        url_for("faq", _external=True),
        url_for("login", _external=True),
        url_for("register", _external=True)
    ]

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>'

    sitemap_xml += (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )

    for page in pages:

        sitemap_xml += f"""
        <url>
            <loc>{page}</loc>
        </url>
        """

    sitemap_xml += "</urlset>"

    return Response(
        sitemap_xml,
        mimetype="application/xml"
    )


# =========================================================
# ROBOTS.TXT
# =========================================================

@app.route("/robots.txt")
def robots():

    return Response(
        """User-agent: *
Allow: /

Sitemap: https://in/sitemap.xml
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