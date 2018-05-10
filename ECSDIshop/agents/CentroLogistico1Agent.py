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

            if accion == ECSDI.PeticionEnvioACentroLogistico:
                prioritat = grafoEntrada.value(subject=content, predicate=ECSDI.Prioridad)

                relacion = grafoEntrada.value(subject=content, predicate=ECSDI.EnvioDe)
                direccion = grafoEntrada.value(subject=content, predicate=ECSDI.Destino)

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

                    grafoFaltan = Graph()
                    grafoFaltan.bind('ECSDI', ECSDI)
                    content = ECSDI['RespuestaEnvioDesdeCentroLogistico' + str(getMessageCount())]
                    grafoFaltan.add((content, RDF.type, ECSDI.RespuestaEnvioDesdeCentroLogistico))
                    grafoFaltan.add((content, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))

                    for stock in graph_query:
                        unitats = stock.UnidadesEnStok
                        print(unitats)
                        ## TODO afegir el producte si unitats >= 1.

                    enviador = getAgentInfo(agn.EnviadorAgent, DirectoryAgent, CentroLogisticoAgent, getMessageCount())

                    respuestaPeticion = send_message(
                        build_message(grafoFaltan, perf=ACL.request, sender=CentroLogisticoAgent.uri,
                                      receiver=enviador.uri,
                                      msgcnt=getMessageCount(),
                                      content=content), enviador.address)



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