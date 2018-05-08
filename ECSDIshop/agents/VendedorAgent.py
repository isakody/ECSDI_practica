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
    port = 9003
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
VendedorAgent = Agent('VendedorAgent',
                    agn.VendedorAgent,
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

#funcion llamada en /comm
@app.route("/comm")
def communication():
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)



    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=VendedorAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el contenido que ha de ser una accion de la ontologia definida en Protege
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            # Si la acción es de tipo peticiónCompra emprendemos las acciones consequentes
            if accion == ECSDI.PeticionCompra:
                logger.info('Recibimos petición de compra')

                # Enviar mensaje con la compra a enviador
                # enviador = getAgentInfo()
                # resultadoComunicacion = send_message(build_message(grafoEntrada,
                #       perf=ACL.request, sender=VendedorAgent.uri, receiver=enviador.uri,
                #       msgcnt=getMessageCount(), content=content), enviador.address)

                tarjeta = grafoEntrada.value(subject=content, predicate=ECSDI.Tarjeta)
                print(tarjeta)

                relacion = grafoEntrada.value(subject=content, predicate=ECSDI.De)
                print(relacion)

                # relacion = grafoEntrada.value(subject=content, predicate=ECSDI.De)

                # relacion = grafoEntrada.objects(content, ECSDI.De)
                # compra = grafoEntrada.objects(content, ECSDI.Compra)

                # compra = grafoEntrada.subjects(RDF.type, ECSDI.Compra)



                compra = grafoEntrada.value(subject=relacion, predicate=ECSDI.Compra)
                print(compra)
                for producto in grafoEntrada.objects(subject=compra, predicate=ECSDI.Producto):
                    print(producto)
                    print(grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre))

                #for r in relacion:
                 #   if grafoEntrada.value(subject=r, predicate=RDF.type) == ECSDI.Compra:
                  #      compra = grafoEntrada.value(subject=r, predicate=RDF.type)
                   #     for producto in compra:
                    #        nombre = grafoEntrada.value(subject=producto, predicate=RDF.Nombre)
                     #       print(nombre)
                      #      precio = grafoEntrada.value(subject=producto, predicate=RDF.Precio)
                       #     print(precio)


                # content = ECSDI['RespuestaCompra' + str(getMessageCount())]

                resultadoComunicacion = Graph()

                # resultadoComunicacion.add((content, RDF.type, ECSDI.RespuestaCompra))


    #no retronamos nada
    logger.info('Respondemos a la petición de compra')
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

#funcion llamada al principio de un agente
def vendedorBehavior(queue):

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

    gr = registerAgent(VendedorAgent, DirectoryAgent, VendedorAgent.uri, getMessageCount())
    return gr

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=vendedorBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=True)

    # Wait behaviors
    ab1.join()
    print('The End')