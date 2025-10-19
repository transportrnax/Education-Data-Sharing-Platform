from flask import jsonify, render_template, request, redirect, url_for, flash
from . import main_bp
from ..extensions import mongo
from flask_login import login_required, current_user
from .help import Help
from bson import ObjectId
from .User import User


@main_bp.route("/")
def index():
    # return jsonify({"message": "Welcome to E-DBA (Flask + MongoDB)!"})
    return render_template("index.html")

@main_bp.route("/home")
def home():
    return render_template("home.html")

@main_bp.route("/ping")
def ping():
    mongo.db.ping.insert_one({"ping": "pong"})
    return jsonify({"message": "pong"})

@main_bp.route('/help', methods=['GET', 'POST'])
@login_required
def help_page():
    if current_user.role.value == 1:  # If TAdmin, redirect to admin help page
        return redirect(url_for('main.admin_help_page'))
    if request.method == 'POST':
        question = request.form.get('question')
        if question:
            Help.create(question, str(current_user.user_id))
            flash('Your question has been submitted successfully!', 'success')
            return redirect(url_for('main.help_page'))

    # For regular users, show their questions
    user_questions = Help.get_user_questions(current_user.user_id)
    return render_template('help/help.html', questions=user_questions)

@main_bp.route('/help/answer/<help_id>', methods=['POST'])
@login_required
def answer_question(help_id):
    print(help_id)
    if current_user.role.value != 1:  # Only TAdmin can answer
        flash('You are not authorized to answer questions.', 'error')
        return redirect(url_for('main.help_page'))
    
    answer = request.form.get('answer')

    help_entry = Help.get_by_id(help_id)
    if not help_entry:
        flash('Question not found.', 'error')
        return redirect(url_for('main.admin_help_page'))
    
    help_entry.answer = answer
    help_entry.save(ObjectId(help_id), answer=help_entry.answer, answer_by=current_user.username)
    flash('Answer submitted successfully.', 'success')
    return redirect(url_for('main.admin_help_page'))

@main_bp.route('/help/admin')
@login_required
def admin_help_page():
    if current_user.role.value != 1:  # Only TAdmin can access
        flash('You are not authorized to view this page.', 'error')
        return redirect(url_for('main.home'))
    
    questions = Help.get_all_questions()
    return render_template('help/admin_help.html', questions=questions)

# @main_bp.route("/search")
# def search():

