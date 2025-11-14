from extensions import db
from datetime import datetime

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    idade = db.Column(db.Integer)
    endereco = db.Column(db.String(255))
    telefone = db.Column(db.String(11))
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    observacoes = db.Column(db.Text)

    data_entrada = db.Column(db.DateTime, default=datetime.utcnow)
    data_saida = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Cliente {self.nome}>"
