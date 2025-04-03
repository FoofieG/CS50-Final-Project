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
