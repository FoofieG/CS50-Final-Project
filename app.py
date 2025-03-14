import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # If amount of stock is 0, delete the row from portfolio
    db.execute("DELETE FROM portfolio WHERE amount = 0")

    # Get all user`s data from users database
    users_data= db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    # Get users balance
    balance = users_data[0]["cash"]

    # Get all of the user`s portfolio
    user_portfolio = db.execute("SELECT * FROM portfolio WHERE user_id = ?", session["user_id"])

    total_balance = balance

    for row in user_portfolio:
        row["price"] = lookup(row["stock_type"])["price"]
        total_balance = total_balance + (row["price"] * row["amount"])
        row["stock_total"] = usd(row["amount"] * row["price"])
        row["price"]= usd(row["price"])

    return render_template("index.html", balance = usd(balance), user_portfolio = user_portfolio, total_balance=usd(total_balance))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        symbol = request.form.get("symbol")

        # Look up the stock symbol using the lookup function
        stock = lookup(symbol)

        # Check if lookup returned None or an invalid result
        if stock is None:
            return apology("No stock found", 400)

        # Look up the amont of shares user entered
        amount_of_shares = request.form.get("shares")

        # Check if user entered something
        if not amount_of_shares:
            return apology("must enter amount of shares", 400)

        try:
            amount_of_shares = int(amount_of_shares)
        except ValueError:
            return apology("Enter a valid number of shares", 400)

        # Display ERROR if the amount of shares is NOT possitive
        if amount_of_shares <= 0:
            return apology("Enter valid amount of shares", 400)

        # Get the list of dictionaries with all user info
        user_info = db.execute(
            "SELECT * FROM users WHERE id = ? ", session["user_id"])

        # Get users balance (0 because there can ONLY be ONE line since id is UNIQUE)
        user_cash_balance = user_info[0]["cash"]

        # Calculate total price of the transaction
        total_price = stock["price"] * amount_of_shares

        # Display ERROR if user has not enough money to buy the amount of shares
        if user_cash_balance < total_price:
            return apology("Not enough cash in balance to buy the amount of shares", 400)

        # Deduct the money from user
        db.execute(
            "UPDATE users SET cash = ? WHERE id = ?", user_cash_balance - total_price, session["user_id"])

        # Insert the transaction to TRANSACTIONS database
        db.execute(
            "INSERT INTO transactions (user_id, stock_type, amount, price_per_stock, total_price, transaction_type) VALUES (?, ?, ?, ?, ?, 'BUY')",
            session["user_id"], stock["symbol"], amount_of_shares, stock["price"], total_price)

        # Update the porfolio
        # If the person already has the share:
        all_portfolio = db.execute("SELECT * FROM portfolio WHERE user_id = ?", session["user_id"])
        for rows in all_portfolio:
            if rows["stock_type"] == stock["symbol"]:
                db.execute(
                "UPDATE portfolio SET amount = ? WHERE user_id = ? AND stock_type = ?",
                rows["amount"] + amount_of_shares, session["user_id"], stock["symbol"]
                )
                break
        # If the person bought the share for the first time (for loop didnt match)
        else:
            db.execute(
                "INSERT INTO portfolio VALUES (?, ?, ?)",
                session["user_id"], stock["symbol"], amount_of_shares)

        return redirect("/")
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get all user`s transactions from transactions database
    user_transactions= db.execute(
        "SELECT * FROM transactions WHERE user_id = ?", session["user_id"])

    for row in user_transactions:
        row["price_per_stock"] = usd(row["price_per_stock"])

    return render_template("history.html", transactions = user_transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Try to look up a stock and display it
        try:
            # Display the stock info
            symbol = lookup(request.form.get("symbol"))
            return render_template("quoted.html", name=symbol["name"], price=usd(symbol["price"]) ,symbol=symbol["symbol"])
        # If return value is "NONE" return apology
        except:
            return apology("No stock found", 400)
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm the password", 400)

        # Ensure password and password confirmation match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Querry the user in the database
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username DOESNT exist
        if len(rows) != 0:
            return apology("username already in use, please select a different one", 400)

        # Add the user to database
        db.execute(
        "INSERT INTO users (username, hash) VALUES (? , ?)",
        request.form.get("username"), generate_password_hash(request.form.get("password"))
        )

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Remember which user has registered and log them in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        ########## GET ENTERED VARIABLE ##########
        symbol = request.form.get("symbol")

        amount_of_shares = request.form.get("shares")

        ########## CHECK ALL CONDITIONS ##########

        # Check if user selected ANY stock
        if not symbol:
            # Display ERROR if user didnt select any stock
            return apology("must select a stock", 400)

        # Check if user has that stock
        owned_stocks = db.execute(
        "SELECT * FROM portfolio WHERE user_id = ?", session["user_id"])

        for row in owned_stocks:
            # If user has the stock, break out and continue
            if str(row["stock_type"]) == str(symbol):
                users_owned_amount_of_share = row["amount"]
                break
        else:
            # Display ERROR if user does not have any amount of that stock
            return apology("You dont own this stock", 400)

        # Check if user entered any amount of shares
        if not amount_of_shares:
            return apology("must enter amount of shares", 400)

        # Check if user entered a possitive number
        if float(amount_of_shares) <= 0:
            # Display ERROR if the amount of shares is NOT possitive
            return apology("Enter valid amount of shares", 400)


        # Check if user has the amount of shares
        if float(amount_of_shares) > float(users_owned_amount_of_share):
            # Display ERROR if user doesnt have the amount of shares
            return apology("You don`t own the amount of shares you entered", 400)

        ########## EXECUTE COMMANDS ON DATABASES ##########

        ##### UPDATE USERS DATABASE #####
        # Remove the amount of stock sold from users portfolio
        db.execute(
            "UPDATE portfolio SET amount = ? WHERE user_id = ? AND stock_type = ?",
                float(users_owned_amount_of_share) - float(amount_of_shares), session["user_id"], symbol
        )
        # Get all users data
        users_data = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        # Get current stock price
        current_stock_price = lookup(symbol)["price"]
        transactions_total = float(amount_of_shares) * float(current_stock_price)

        # Add balance to users data
        db.execute(
            "UPDATE users SET cash = ? WHERE id = ? ",
                users_data[0]["cash"] + transactions_total, session["user_id"],
        )

        ##### UPDATE TRANSACTIONS DATABASE #####
        db.execute(
            "INSERT INTO transactions (user_id, stock_type, amount, price_per_stock, total_price, transaction_type) VALUES (?, ?, ?, ?, ?, 'SELL')",
            session["user_id"], symbol, amount_of_shares, current_stock_price, transactions_total)

        # Redirect user to home page
        return redirect("/")

    else:
        # Get all user`s owned stock symbols from users database
        stock_symbols = db.execute(
        "SELECT stock_type FROM portfolio WHERE user_id = ?", session["user_id"])

        return render_template("sell.html", quotes=stock_symbols)


@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    """Change password"""
    if request.method == "POST":

        ########## USER INPUT ##########
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        new_confirmation = request.form.get("new_confirmation")

        ########## ALL IF STATEMENTS ##########
        # Ensure old password was provided
        if not old_password:
            return apology("must provide old password", 400)

        # Ensure new password was submitted
        elif not new_password:
            return apology("must provide new password", 400)

        # Ensure password confirmation was submitted
        elif not new_confirmation:
            return apology("must confirm the new password", 400)

        # Ensure password and password confirmation match
        elif new_password != new_confirmation:
            return apology("new passwords do not match", 400)

        # Querry the user in the database and get his password hash
        user_hash = db.execute("SELECT hash FROM users WHERE id = ?", session["user_id"])

        # Make sure the query returns one result
        if len(user_hash) != 1:
            return apology("User not found", 400)

        # Extract the hash from the result (which is a list of dictionaries)
        hash_value = user_hash[0]["hash"]

        # Compare the old password with the hash
        if not check_password_hash(hash_value, old_password):
            return apology("Incorrect password", 400)

        ########## EXECUTE COMMANDS ON DATABASES TO CHANGE USERS PASSWORD ##########

        db.execute("UPDATE users SET hash = ? WHERE id = ?", generate_password_hash(new_password), session["user_id"])

        # Redirect user to home page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("change_password.html")
