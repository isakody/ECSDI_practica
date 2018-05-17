# -*- coding: utf-8 -*-
"""
filename: userPersonalAgent

Agente que interactua con el usuario.


@author: Borja Fernández
"""
import random

import sys
from utils.ACLMessages import getAgentInfo, build_message, send_message, get_message_properties
from utils.OntologyNamespaces import ECSDI
import argparse
import socket
from multiprocessing import Process
from flask import Flask, render_template, request
from rdflib import Graph, Namespace, RDF, URIRef, Literal, XSD
from utils.Agent import Agent
from utils.FlaskServer import shutdown_server
from utils.Logging import config_logger
from rdflib.namespace import RDF
from utils.OntologyNamespaces import ACL

__author__ = 'ECSDIstore'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default=socket.gethostname(), help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9030
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9000
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

# Flask stuff
app = Flask(__name__, template_folder='../templates')

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
VendedorPersonalAgent = Agent('VendedorPersonalAgent',
                          agn.VendedorPersonalAgent,
                          'http://%s:%d/comm' % (hostname, port),
                          'http://%s:%d/Stop' % (hostname, port))
# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()

# Productos enconctrados
listaDeProductos = []

# Función que lleva y devuelve la cuenta de mensajes
def getMessageCount():
    global mss_cnt
    if mss_cnt is None:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt

# Función que devuelve la página principal de ECSDIstore
@app.route("/", methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('vendedorIndex.html')
    else:
        if request.form['submit'] == 'Submit':
            logger.info("Atendiendo petición de ingreso de producto")
            nombreProducto = request.form['nombreProducto']
            tarjeta = request.form['tarjeta']
            descripcion = request.form['descripcionProducto']
            peso = request.form['peso']
            numeroUnidades = request.form['numeroUnidades']
            precio = request.form['precio']
            desdeCentros = False
            if request.form.getlist('lugarEnvio')[0] == 'envio':
                desdeCentros = True;
            contenido = ECSDI['ProductoExterno'+str(getMessageCount())]
            grafoContenido = Graph();
            grafoContenido.add(contenido, RDF.type,ECSDI.Producto)
            grafoContenido.add(contenido,RDF.type,ECSDI.ProductoExterno)
            grafoContenido.add(contenido,ECSDI.Nombre,Literal(nombreProducto,datatype=XSD.string))
            grafoContenido.add(contenido,ECSDI.Precio,Literal(precio,datatype=XSD.float))
            grafoContenido.add(contenido,ECSDI.Peso,Literal(peso,datatype=XSD.float))
            grafoContenido.add(contenido,ECSDI.Descripcion,Literal(descripcion,datatype=XSD.string))

            sujetoVendedor = ECSDI['Vendedor'+str(getMessageCount())]
            grafoContenido.add(sujetoVendedor,RDF.type,ECSDI.Vendedor)
            grafoContenido.add(sujetoVendedor,ECSDI.Tarjeta,Literal(tarjeta,datatype=XSD.int))
            grafoContenido.add(contenido,ECSDI.VendidoPor,URIRef(sujetoVendedor))


            



            return render_template('procesandoArticulo.html')



# Función de parado del agente
@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"

# Función llamada antes de parar el servidor
def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass

# Funcion para la comunicación
@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion del agente
    """
    return "Ruta de comunicación"

#función llamada antes de cerrar el servidor
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

# Comportamiento del agente
def agentbehavior1():
    """
    Un comportamiento del agente

    :return:
    """

if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1)
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port, debug=True)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
