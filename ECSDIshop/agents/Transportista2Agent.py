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
from multiprocessing import Queue, Process
from datetime import datetime, timedelta

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
    port = 9021
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9020
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
Transportista2Agent = Agent('Transportista2Agent',
                    agn.Transportista2Agent,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
TransportistaDirectoryAgent = Agent('TransportistaDirectoryAgent',
                       agn.TransportistaDirectory,
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


@app.route("/comm")
def communication():
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)
    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = Graph()

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=Transportista2Agent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=TransportistaDirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            if accion == ECSDI.PeticionOfertaTransporte:
                logger.info('Peticion Oferta Transporte')
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                oferta = prepararOferta(grafoEntrada, content)

                resultadoComunicacion = oferta

            elif accion == ECSDI.PeticionEnvioLote:
                logger.info('Peticion Envio Lote')
                logger.info('Su pedido llegara el dia:')
                logger.info(str(datetime.now() + timedelta(days=1)))
                logger.info('Soy el transportista:')
                logger.info(Transportista2Agent.name)

    logger.info('Respondemos a la petición de oferta')
    serialize = resultadoComunicacion.serialize(format='xml')
    return serialize, 200

#funcion llamada en /comm
def prepararOferta(grafoEntrada, content):
    lote = grafoEntrada.value(subject=content, predicate=ECSDI.Para)
    peso = grafoEntrada.value(subject=lote, predicate=ECSDI.Peso)
    print("Peso lote")
    print peso

    precio = calcularOferta(float(peso))

    grafoOferta = Graph()
    grafoOferta.bind('default', ECSDI)
    contentOferta = ECSDI['RespuestaOfertaTransporte'+ str(getMessageCount())]
    grafoOferta.add((contentOferta, RDF.type, ECSDI.RespuestaOfertaTransporte))
    grafoOferta.add((contentOferta, ECSDI.Precio, Literal(precio, datatype=XSD.float)))


    return grafoOferta

def calcularOferta(peso):
    oferta = 15 + peso
    return oferta

@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"

#funcion llamada al principio de un agente
def transportistaBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()

#función llamada antes de cerrar el servidor
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass
#función para registro de agente en el servicio de directorios
def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = registerAgent(Transportista2Agent, TransportistaDirectoryAgent, Transportista2Agent.uri, getMessageCount())
    return gr

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=transportistaBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')