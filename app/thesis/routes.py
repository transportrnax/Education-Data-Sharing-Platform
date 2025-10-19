from flask import render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
import os
from . import thesis_bp
from app.extensions import get_db


@thesis_bp.route('/')
def list_theses():
	db = get_db()

	# Config query parameters
	page = int(request.args.get('page', default=1))
	per_page = 10
	skip = (page - 1) * per_page

	# Make paged query
	cursor = db.Theses.find({"available": True},
	                        {"_id": True, "title": True, "author": True, "available": True}).skip(skip).limit(per_page)
	theses = list(cursor)

	# Get total theses stats
	total = db.Theses.count_documents({})
	total_pages = (total + per_page - 1) // per_page

	return render_template('thesis/list.html',
	                       theses=theses,
	                       page=page,
	                       total_pages=total_pages)

@thesis_bp.route('/api/list')
def api_list():
	db = get_db()
	page = int(request.args.get('page', 1))
	per_page = int(request.args.get('per_page', 10))
	skip = (page - 1) * per_page

	cursor = db.Theses.find({'available': True}, {
		'location': False,
		'available': False
	}).skip(skip).limit(per_page)

	total = db.Theses.count_documents()
	theses = [{
		'id': str(thesis['_id']),
		'title': thesis['title'],
		'author': thesis['author'],
		'abstract': thesis['abstract'],
		'price': thesis['price']
	} for thesis in cursor]

	return jsonify({
		'total': total,
		'page': page,
		'total_pages': (total + per_page - 1) // per_page,
		'theses': theses
	})

@thesis_bp.route('/<thesis_id>')
@login_required
def view_thesis(thesis_id):
	db = get_db()
	thesis = db.Theses.find_one({"_id": thesis_id})
	if not thesis:
		flash("Error: This thesis doesn't exist.", "error")
		return redirect(url_for('thesis.list_theses'))
	return render_template('thesis/detail.html', thesis=thesis)


@thesis_bp.route('/<thesis_id>/pay', methods=['GET', 'POST'])
@login_required
def pay_thesis(thesis_id):
	db = get_db()
	thesis = db.Theses.find_one({"_id": thesis_id})
	if request.method == 'POST':
		# TODO: Complete actual payment function
		db.ThesisPurchases.insert_one({
			"user_id": current_user.get_id(),
			"thesis_id": thesis_id,
			"status": "success"
		})
		flash("Payment succeeded! You may download this thesis now.", "success")
		return redirect(url_for('thesis.download_thesis', thesis_id=thesis_id))

	return render_template('thesis/pay.html', thesis=thesis)


@thesis_bp.route('/<thesis_id>/download')
@login_required
def download_thesis(thesis_id):
	db = get_db()
	purchase = db.ThesisPurchases.find_one({
		"user_id": current_user.get_id(),
		"thesis_id": thesis_id,
		"status": "success"
	})
	if not purchase:
		flash("You must buy this thesis before download.", "error")
		return redirect(url_for('thesis.view_thesis', thesis_id=thesis_id))

	thesis = db.Theses.find_one({"_id": thesis_id})
	return send_file(os.path.join("static", thesis["location"]), as_attachment=True)
