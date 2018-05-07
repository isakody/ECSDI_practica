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
    port = 9081
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
UserPersonalAgent = Agent('UserPersonalAgent',
                          agn.UserPersonalAgent,
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
productosEncontrados = []

# Función que lleva y devuelve la cuenta de mensajes
def getMessageCount():
    global mss_cnt
    if mss_cnt is None:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt

# Función que devuelve la página principal de ECSDIstore
@app.route("/")
def index():
    return render_template('indexAgentePersonal.html')

# Función que atiende a peticiones GET Y POST de busqueda, GET para coger la página que nos permite ver el filtro
# y post para procesar las peticiones de filtrado
@app.route("/search", methods=['GET', 'POST'])
def search():
    if request.method == 'GET':
        return render_template('search.html', products = None)
    elif request.method == 'POST':
        if request.form['submit'] == 'Search':
            logger.info("Enviando petición de busqueda")
            contenido = ECSDI['BuscarProducto'+ str(getMessageCount())]
            grafoDeContenido = Graph()
            grafoDeContenido.add((contenido,RDF.type,ECSDI.BuscarProducto))
            nombreProducto = request.form['nombre']

            # Añadimos el nombre del producto por el que filtraremos
            if nombreProducto :
                print(nombreProducto)
                nombreSujeto = ECSDI['RestriccionDeNombre' + str(getMessageCount())]
                grafoDeContenido.add((nombreSujeto, RDF.type, ECSDI.RestriccionDeNombre))
                grafoDeContenido.add((nombreSujeto, ECSDI.Nombre, Literal(nombreProducto, datatype=XSD.string)))
                grafoDeContenido.add((contenido, ECSDI.RestringidaPor, URIRef(nombreSujeto)))

            precioMin = request.form['minPrecio']
            precioMax = request.form['maxPrecio']
            # Añadimos el rango de precios por el que buscaremos
            if precioMax or precioMin:
                print(precioMax)
                print(precioMin)
                precioSujeto = ECSDI['RestriccionDePrecio' + str(getMessageCount())]
                grafoDeContenido.add((precioSujeto, RDF.type, ECSDI.RestriccionDePrecio))
                if precioMin:
                    grafoDeContenido.add((precioSujeto, ECSDI.PrecioMinimo, Literal(precioMin)))
                if precioMax:
                    grafoDeContenido.add((precioSujeto, ECSDI.PrecioMaximo, Literal(precioMax)))
                grafoDeContenido.add((contenido, ECSDI.RestringidaPor, URIRef(precioSujeto)))

            # Pedimos que nos se nos busque la información del agente filtrador
            agente = getAgentInfo(agn.FilterAgent, DirectoryAgent, UserPersonalAgent, getMessageCount())
            # Enviamos petición de filtrado al agente filtrador
            grafoBusqueda = send_message(
                build_message(grafoDeContenido, perf=ACL.request, sender=UserPersonalAgent.uri, receiver=agente.uri,
                              msgcnt=getMessageCount(),
                              content=contenido), agente.address)
            # Falta mostrar el restultado de busqueda en el html
            listaProductos = []
            posicionDeSujetos = {}
            indice = 0
            for s, p, o in grafoBusqueda:
                print(s,p,o)
                if s not in posicionDeSujetos:
                    posicionDeSujetos[s] = indice
                    indice += 1
                    listaProductos.append({})
                else :
                    producto = listaProductos[posicionDeSujetos[s]]
                    if p == ECSDI.Nombre:
                        producto["Nombre"] = o
                    elif p == ECSDI.Precio:
                        producto["Precio"] = o
                    elif p == ECSDI.Descripcion:
                        producto["Descripcion"] = o
                    elif p == RDF.type:
                        producto["Sujeto"] = s
                    listaProductos[posicionDeSujetos[s]] = producto
            return render_template('search.html', products = listaProductos)
        elif request.form['submit'] == 'Buy':
            listaDeCompra = []
            for producto in request.form.getlist("checkbox"):
                prod = []
                prod.append(producto[0])




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
