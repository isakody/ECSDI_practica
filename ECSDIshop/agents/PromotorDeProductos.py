# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
import datetime
import socket
import sys
import thread
import threading
from multiprocessing import Queue, Process
from random import randint
from time import sleep

from flask import Flask, request
from rdflib import URIRef, XSD

from utils.ACLMessages import *
from utils.Agent import Agent
from utils.FlaskServer import shutdown_server
from utils.Logging import config_logger
from utils.OntologyNamespaces import ECSDI
from datetime import datetime, timedelta
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
    port = 9040
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
PromotorDeProductosAgent = Agent('PromotorDeProductos',
                    agn.PromotorDeProductos,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))
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
    gr = registerAgent(PromotorDeProductosAgent, DirectoryAgent, PromotorDeProductosAgent.uri, getMessageCount())
    return gr

@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=PromotorDeProductosAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            graph = Graph()
            seleccion = randint(0, 1)
            if seleccion == 1:
                ontologyFile = open('../data/FiltrosDB')
            else:
                ontologyFile = open('../data/ComprasDB')
            graph.parse(ontologyFile, format='turtle')
            query =  """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                        PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                        SELECT ?Producto ?Nombre ?Precio ?Descripcion
                        where {
                            ?Producto rdf:type default:Producto .
                            ?Producto default:Nombre ?Nombre .
                            ?Producto default:Precio ?Precio .
                            ?Producto default:Descripcion ?Descripcion .

                        }
                        GROUP BY ?Nombre ORDER BY DESC(COUNT(*)) LIMIT 10"""

            resultadoConsulta = graph.query(query)
            resultadoComunicacion = Graph()
            sujeto2 = ECSDI["RespuestaRecomendacion"+str(getMessageCount())]
            for product in resultadoConsulta:
                product_nombre = product.Nombre
                product_precio = product.Precio
                product_descripcion = product.Descripcion
                sujeto = product.Producto
                resultadoComunicacion.add((sujeto, RDF.type, ECSDI.Producto))
                resultadoComunicacion.add((sujeto, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
                resultadoComunicacion.add((sujeto, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
                resultadoComunicacion.add((sujeto, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))
                resultadoComunicacion.add((sujeto2,ECSDI.Recomienda,URIRef(sujeto)))

    logger.info('Respondemos a la petición de busqueda')
    serialize = resultadoComunicacion.serialize(format='xml')
    return serialize, 200



@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"

def comprobarYValorar():
    graph = Graph()
    ontologyFile = open('../data/EnviosDB')
    logger.info("Comprobando productos recibidos")
    graph.parse(ontologyFile, format='turtle')
    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT DISTINCT ?Producto ?Nombre ?Precio ?Descripcion
                            where {
                                ?PeticionEnvio rdf:type default:PeticionEnvio .
                                ?PeticionEnvio default:Tarjeta ?Tarjeta .
                                ?PeticionEnvio default:De ?Compra .
                                ?PeticionEnvio default:FechaEntrega ?FechaEntrega .
                                ?Compra default:Contiene ?Producto .
                                ?Producto default:Nombre ?Nombre .
                                ?Producto default:Precio ?Precio .
                                ?Producto default:Descripcion ?Descripcion .
                            FILTER("""
    query += """ ?FechaEntrega > '""" + str(datetime.now() - timedelta(days=1)) + """'^^xsd:date"""
    query += """)}"""

    resultadoConsulta = graph.query(query)
    grafoConsulta = Graph()
    logger.info("Haciendo petición de valoracion")
    accion = ECSDI["PeticionValoracion"+str(getMessageCount())]
    grafoConsulta.add((accion,RDF.type,ECSDI.PeticionValoracion))
    graph2 = Graph()
    ontologyFile2 = open('../data/ValoracionesDB')
    graph2.parse(ontologyFile2, format='turtle')
    productList = []
    for a, b,c in graph2:
        productList.append(a)
    contador = 0
    for g in resultadoConsulta:
        if g.Producto not in productList:
            contador = contador + 1
            grafoConsulta.add((g.Producto,RDF.type,ECSDI.Producto))
            grafoConsulta.add((accion,ECSDI.Valora,URIRef(g.Producto)))
    if contador != 0:
        # Obtenemos información del usuario
        agente = getAgentInfo(agn.UserPersonalAgent, DirectoryAgent, PromotorDeProductosAgent, getMessageCount())
        # Obtenemos las valoraciones del usuario
        logger.info("Enviando petición de valoracion")
        resultadoComunicacion = send_message(build_message(grafoConsulta,
                                                           perf=ACL.request, sender=PromotorDeProductosAgent.uri,
                                                           receiver=agente.uri,
                                                           msgcnt=getMessageCount(), content=accion), agente.address)
        logger.info("Recibido resultado de valoracion")
        for s, o, p in resultadoComunicacion:
            if o == ECSDI.Valoracion:
                graph2.add((s,o,p))
        logger.info("Registrando valoraciones")
        graph2.serialize(destination='../data/ValoracionesDB', format='turtle')
        logger.info("Registro valoraciones finalizada")


def solicitarValoraciones():
    logger.info("Iniciando petición rutinaria de valoraciones")
    thread = threading.Thread(target=comprobarYValorar)
    thread.start()
    logger.info("Petición rutinaria de valoraciones finalizada")
    thread.join()
    sleep(120)

    solicitarValoraciones()
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

def PromotorBehaviour(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()


if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    thread = threading.Thread(target=solicitarValoraciones)
    thread.start()
    ab1 = Process(target=PromotorBehaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    thread.join()
    print('The End')