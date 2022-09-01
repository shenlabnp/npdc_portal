#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for, flash
import pandas as pd
from datetime import datetime

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('query', __name__)


@blueprint.route("/query", methods=['POST', 'GET'])
def page_main():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    # if submitting a job
    if request.method == 'POST':
        
        # validate and parse input sequences
        input_validated, input_proteins = parse_input_prots(request.form["protsequences"])

        if not input_validated:
            flash("Failed to submit query: please check your input sequences", "alert-danger")
            return redirect(url_for("query.page_main"))

        # check if user have a pending submitted job

        # check if user have recently submitted job

        # submit the new job
        job_id = submit_new_job(session["userid"], input_proteins)

        # redirect to the job's page
        return redirect(url_for("query.page_job", job_id=job_id))

        
    # page title
    page_title = "BLAST Query"
    page_subtitle = ("")

    # render view
    return render_template(
        "query/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )

@blueprint.route("/query/result/<int:job_id>")
def page_job(job_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    # get job data
    job_data = pd.read_sql((
        "SELECT jobs.*,status_enum.name as status_desc FROM jobs,status_enum"
        " WHERE userid=? AND id=? and jobs.status=status_enum.code"
    ), sqlite3.connect(conf["query_db_path"]), params=(session["userid"], job_id))

    if job_data.shape[0] != 1:
        flash("Can't find the specified job id", "alert-danger")
        return redirect(url_for("query.page_main"))

    job_data = job_data.iloc[0].to_dict()

    # page title
    page_title = "Query result: job #{}".format(job_id)
    page_subtitle = ("")

    # render view
    return render_template(
        "query/job.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        auto_refresh=(job_data["status"] < 2),
        job_data=job_data
    )

    return str(job_id)


def parse_input_prots(prot_seq):
    results = {
        "prot_1": "MRHRLKMGVVANDVTVTDPDRGLLPASGSAALHRYAAYHVTGGLDLDALRTAWRAVAGDGAPVEPAAVGQTAGEGFGDEELCARWAARPFAEGDAPARLHLARRGPREHLLLLAASHSGAWEGPSGALPAALSDAYRAVVTGGRPSAPPLRPAPGTRGGEEPSATAAGLVLPADRNRPHLPPHAGGAVAFTWSPDLGFRTARLAEAAGVTPAAVVLAGFRALVHRYAGQDDGTLSTAFRELLRTVPDPASKPCRIEGADAVFVHRERAALRIPGAEVRQLSVHNGTAAADLALVLQDTAPCVAGFLEYRAALFEPASARRLLDQLATLLAAATADPDAPVGGLPLDDERHRDRALRASDRRAPRGHVTPPVHVSVRGHAGQDGTAVSFGGVSTGYAELTAHAARVASALTAAGAGPGSPVAVRMRPGAHRIAVLLGVLEAGAHLAWFAPDGGGERHRSMLRDLRPSCMVLDGGPQEDPLALWYAGEPGARLLDASQVLGSPSAAPGADAAAGARPDPEDLAYVAFTSGSTGRPKGIVQSHAALAQFAGWMGEQFAMGPGARVAQWVSPEHDPALAEVFATLVAGGTLCPVPERVRVNPDKLVPWLVQEGITHIQTVPSFARDLLGVITGSGPDRRPDALSHLLLMGEALPGELVDGLRAALPRTRLINLYGPTETIAATWHEITGPVAGQVPIGRPLPGRQVLVVDEHDRPSPAGVTGELVVRSPYVTPGYLAVEGGPDHGALFAPVAGFAPDGDRWYRTGDLARVRFDGALEFRGRSDFQVKLFGNRVELTEIEAALNRDPSVLECAVLPHVNGQGLVTRLAVYVVPRGDGEGDVNADVRAWRSHLRGQFGPLTLPAVFTRLSSRLPRNAAGKVDRSQLTR",
        "prot_2": "MQAWFKRTSGVPGDRRGKWLVLAAWLIIAMALGPLAGKLADVQDSSANAFLPRSSESAKLNKELEKFRADELMPAVVVYSADGSLPAEGRAKAEKDIAAFQELAAEGEKVEAPLESKDGQALMVVVPLISDADIVATTKKVRDIADANAPPGVAVEVGGPAGSTTDAAGAFESLDSMLMMVTGLVVAVLLLITYRSPILWLLPLLSVGFASVLTQVGTYMLAKYAGLPVDPQSSGVLMVLVFGVGTDYALLLIARYREELRREQDRHIAMKTALRRSGPAILASAGTIAIGLVCLVLADVNSSRSMGLVGAIGVVCAFLAMVTILPALLVILGRWVFWPFVPRWTAEAAAAPEAPASHSRWERIGSVTAARPRRAWVLSLAATGLLALSSLGLDMGLTQSELLQTKPESVVAQERISAHYPSGSSDPATVVTPTADAAEVRRAAEGTEGVVSVEDGPTTPDGELTLLSVVLKDVPDSAGAKDTVDALRDNTDALVGGTTAQSLDTQRASVRDLWVTVPAVLLVVLLVLIWLLRSVAGPLIMLGTVVVSFFAALGASNLLFEHVMGHAGVDWSVPLLGFVYLVALGIDYNIFLMHRVKEEVALHGHAKGVLTGLTTTGGVITSAGVVLAATFAVIASLPLVPMAQMGVVVGLGILLDTFLVRTILLPALALDLGPRFWWPGALSKAAGGPTPVREDRTSQPVG"
    }
    return True, results


def submit_new_job(user_id, input_proteins):
    
    with sqlite3.connect(conf["query_db_path"]) as con:

        # submit job and get the new id back
        cur = con.cursor()
        cur.execute((
            "INSERT INTO jobs (userid, submitted, status)"
            " VALUES (?, ?, ?)"
        ), (user_id, datetime.now(), -2))
        con.commit()
        job_id = cur.lastrowid

        # submit protein sequences
        cur.executemany((
            "INSERT INTO query_proteins (jobid, name, aa_seq)"
            " VALUES (?, ?, ?)"
        ), (
            [(job_id, name, aa_seq) for name, aa_seq in input_proteins.items()]
        ))
        con.commit()

        # update job status so the workers will pick it up
        cur.execute((
            "UPDATE jobs SET status=?"
            " WHERE id=?"
        ), (0, job_id))
        con.commit()

    return job_id