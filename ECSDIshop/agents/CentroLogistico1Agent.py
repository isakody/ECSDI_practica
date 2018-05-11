# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
import socket
import sys
import threading
from multiprocessing import Queue, Process
from time import sleep

from flask import Flask, request
from rdflib import URIRef, XSD

from utils.ACLMessages import *
from utils.Agent import Agent
from utils.FlaskServer import shutdown_server
from utils.Logging import config_logger
from utils.OntologyNamespaces import ECSDI
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
    port = 9004
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

# AGENT ATTRIBUTES ----------------------------------------------------------------------------------------

# Agent Namespace
agn = Namespace("http://www.agentes.org#")

# Message Count
mss_cnt = 0

# Data Agent
# Datos del Agente
CentroLogisticoAgent = Agent('CentroLogisticoAgent',
                    agn.CentroLogisticoAgent,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

CentroLogisticoDirectoryAgent = Agent('CentroLogisticoDirectoryAgent',
                       agn.CentroLogisticoDirectory,
                       'http://%s:9010/Register' % (hostname),
                       'http://%s:9010/Stop' % (hostname))

# Global triplestore graph
dsGraph = Graph()

# Queue
queue = Queue()

# Flask app
app = Flask(__name__)

#función inclremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')
    gr = registerAgent(CentroLogisticoAgent, CentroLogisticoDirectoryAgent, CentroLogisticoAgent.uri, getMessageCount())
    gr = registerAgent(CentroLogisticoAgent, DirectoryAgent, CentroLogisticoAgent.uri, getMessageCount())
    return gr

@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """

    logger.info('Peticion de informacion recibida')
    global dsGraph

    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProp = get_message_properties(grafoEntrada)

    if messageProp is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        res = build_message(Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProp['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            res = build_message(Graph(),
                               ACL['not-understood'],
                               sender=CentroLogisticoDirectoryAgent.uri,
                               msgcnt=getMessageCount())
        else:
            content = messageProp['content']
            # Averiguamos el tipo de la accion
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            print(accion)

            if accion == ECSDI.PeticionEnvioACentroLogistico:

                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                responderPeticionEnvio(grafoEntrada, content)


def responderPeticionEnvio(grafoEntrada, content):
    for a, b, c in grafoEntrada:
        print(a, b, c)

    prioritat = grafoEntrada.value(subject=content, predicate=ECSDI.Prioridad)

    relacion = grafoEntrada.value(subject=content, predicate=ECSDI.EnvioDe)
    direccion = grafoEntrada.value(subject=content, predicate=ECSDI.Destino)

    grafoFaltan = Graph()
    grafoFaltan.bind('ECSDI', ECSDI)
    contentR = ECSDI['RespuestaEnvioDesdeCentroLogistico' + str(getMessageCount())]
    grafoFaltan.add((contentR, RDF.type, ECSDI.RespuestaEnvioDesdeCentroLogistico))
    grafoFaltan.add((contentR, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))

    grafoEnviar = Graph()
    grafoEnviar.bind('ECSDI', ECSDI)

    for producto in grafoEntrada.objects(subject=relacion, predicate=ECSDI.Contiene):
        nombreP = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)

        # QUERY
        # Mirar que el que retorna la query sigui un stock amb num de tal >= 1

        graph = Graph()
        ontologyFile = open('../data/StockDB.owl')
        graph.parse(ontologyFile, format='turtle')

        addAnd = False;

        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX owl: <http://www.w3.org/2002/07/owl#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT ?Producto ?Nombre ?UnidadesEnStok
                            where {
                                ?Stock rdf:type default:Stock .
                                ?Stock default:UnidadesEnStok ?UnidadesEnStok .
                                ?Stock default:Producto ?Producto .
                                ?Producto default:Nombre ?Nombre .
                                FILTER("""

        if nombreP is not None:
            query += """?Nombre = '""" + nombreP + """'"""
            addAnd = True

        query += """)}"""

        graph_query = graph.query(query)

        for stock in graph_query:
            unitats = stock.UnidadesEnStok
            producto = stock.Tiene
            print(unitats)


            if unitats == 0:
                sujetoProducto = ECSDI['Producto' + str(getMessageCount())]
                grafoFaltan.add((sujetoProducto, RDF.type, ECSDI.Producto))
                grafoFaltan.add((sujetoProducto, ECSDI.Descripcion, producto.Descripcion))
                grafoFaltan.add((sujetoProducto, ECSDI.Nombre, producto.Nombre))
                grafoFaltan.add((sujetoProducto, ECSDI.Precio, producto.Precio))
                grafoFaltan.add((sujetoProducto, ECSDI.Peso, producto.Peso))
                grafoFaltan.add((contentR, ECSDI.Faltan, URIRef(sujetoProducto)))

            else:
                contentEnviar = ECSDI['ProductoPendiente' + str(getMessageCount())]
                grafoEnviar.add((contentEnviar, RDF.type, ECSDI.ProductoPendiente))
                grafoEnviar.add((contentEnviar, ECSDI.Descripcion, producto.Descripcion))
                grafoEnviar.add((contentEnviar, ECSDI.Nombre, producto.Nombre))
                grafoEnviar.add((contentEnviar, ECSDI.Precio, producto.Precio))
                grafoEnviar.add((contentEnviar, ECSDI.Peso, producto.Peso))
                grafoEnviar.add((contentEnviar, ECSDI.EnviarA, direccion))
                # TODO baixar 1 el stock

    # TODO guardar el grafoEnviar a ProductosPendientes
    thread1 = threading.Thread(target=crearLote, args=(grafoEnviar,))
    thread1.start()

    return grafoFaltan


def crearLote(grafoEnviar):
    grafoLote = Graph()
    content = ECSDI['LoteProductos' + str(getMessageCount())]
    grafoLote.add((content, RDF.type, ECSDI.LoteProductos))
    peso = 0
    prioridad = 0

    for prodPendiente in grafoEnviar.subjects(RDF.type, ECSDI.ProductoPendiente):
        prioridad = prodPendiente.Prioridad
        sujetoP = ECSDI['Producto' + str(getMessageCount())]
        grafoLote.add((sujetoP, RDF.type, ECSDI.Producto))
        grafoLote.add((sujetoP, ECSDI.Descripcion, prodPendiente.Descripcion))
        grafoLote.add((sujetoP, ECSDI.Nombre, prodPendiente.Nombre))
        grafoLote.add((sujetoP, ECSDI.Precio, prodPendiente.Precio))
        grafoLote.add((sujetoP, ECSDI.Peso, prodPendiente.Peso))
        grafoLote.add((content, ECSDI.CompuestoPor, URIRef(sujetoP)))
        peso += prodPendiente.Peso

    grafoLote.add((content, ECSDI.Peso, peso))
    grafoLote.value((content, ECSDI.Prioridad, prioridad))

    transportista = getAgentInfo(agn.TransportistaDirectoryService, DirectoryAgent, CentroLogisticoAgent, getMessageCount())






# Aixo servira per agafar els productes pendents i ordenar-los en lots
def crearLotes():
    graph = Graph()
    ontologyFile = open('../data/ProductosPendientesDB.owl')
    graph.parse(ontologyFile, format='turtle')

    addAnd = False;

    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                                PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                                SELECT ?Producto ?Nombre ?UnidadesEnStok
                                where {
                                    ?Stock rdf:type default:Stock .
                                    ?Stock default:UnidadesEnStok ?UnidadesEnStok .
                                    ?Stock default:Producto ?Producto .
                                    ?Producto default:Nombre ?Nombre .
                                }"""


    return


@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"


def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

def centroLogistico1Behaviour(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()


if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=centroLogistico1Behaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=True)

    # Wait behaviors
    ab1.join()
    print('The End')