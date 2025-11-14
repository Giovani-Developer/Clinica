from flask import Flask, render_template, redirect, url_for, request
from extensions import db
from models import Client
from datetime import datetime

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///clientes.db"
app.config["SECRET_KEY"] = "secret"

db.init_app(app)

with app.app_context():
    db.create_all()


@app.route("/", methods=["GET"])
def index():
    busca = request.args.get("busca", "")

    if busca:
        busca_formatada = f"%{busca}%"
        clientes = Client.query.filter(
            db.or_(
                Client.nome.ilike(busca_formatada),
                Client.cpf.ilike(busca_formatada),
                Client.telefone.ilike(busca_formatada),
                Client.endereco.ilike(busca_formatada),
            )
        ).all()
    else:
        clientes = Client.query.all()

    return render_template("index.html", clientes=clientes, busca=busca)



@app.route("/novo", methods=["GET", "POST"])
def novo_cliente():
    if request.method == "POST":
        nome = request.form.get("nome")
        idade = request.form.get("idade")
        endereco = request.form.get("endereco")
        telefone = request.form.get("telefone")
        cpf = request.form.get("cpf")
        observacoes = request.form.get("observacoes")

        novo = Client(
            nome=nome,
            idade=idade,
            endereco=endereco,
            telefone=telefone,
            observacoes=observacoes,
            cpf=cpf
        )

        db.session.add(novo)
        db.session.commit()

        return redirect(url_for("index"))

    return render_template("new_client.html")


@app.route("/cliente/<int:id>")
def cliente(id):
    cliente = Client.query.get_or_404(id)
    return render_template("client_detail.html", cliente=cliente)


@app.route("/saida/<int:id>")
def registrar_saida(id):
    cliente = Client.query.get_or_404(id)
    cliente.data_saida = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("cliente", id=id))


@app.route("/excluir/<int:id>", methods=["POST"])
def excluir_cliente(id):
    cliente = Client.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    return redirect(url_for("index"))


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar_cliente(id):
    cliente = cliente.query.get_or_404(id)
    
    if request.method == 'POST':
        cliente.nome = request.form['nome']
        cliente.idade = request.form['idade']
        cliente.endereco = request.form['endereco']
        cliente.telefone = request.form['telefone']
        cliente.cpf = request.form['cpf']
        cliente.observacoes = request.form['observacoes']
        
        db.session.commit()
        return redirect(url_for('ficha_cliente', id=cliente.id))
    
    return render_template('editar_cliente.html', cliente=cliente)




if __name__ == "__main__":
    app.run(debug=True)
