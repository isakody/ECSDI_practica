# -*- coding: utf-8 -*-
"""
filename: userPersonalAgent

Agente que interactua con el usuario.


@author: Borja Fernández
"""
import random

import sys
from utils.ACLMessages import *
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
listaDeProductos = []

# Función que lleva y devuelve la cuenta de mensajes
def getMessageCount():
    global mss_cnt
    if mss_cnt is None:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt

# Función que solicita una petición de busqueda al agente correspondiente
def enviarPeticionBusqueda(request):
    global listaDeProductos
    logger.info("Enviando petición de busqueda")
    contenido = ECSDI['BuscarProducto' + str(getMessageCount())]
    grafoDeContenido = Graph()
    grafoDeContenido.add((contenido, RDF.type, ECSDI.BuscarProducto))
    nombreProducto = request.form['nombre']

    # Añadimos el nombre del producto por el que filtraremos
    if nombreProducto:
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
    listaDeProductos = []
    posicionDeSujetos = {}
    indice = 0
    for s, p, o in grafoBusqueda:
        if s not in posicionDeSujetos:
            posicionDeSujetos[s] = indice
            indice += 1
            listaDeProductos.append({})
        if s in posicionDeSujetos:
            producto = listaDeProductos[posicionDeSujetos[s]]
            if p == ECSDI.Nombre:
                producto["Nombre"] = o
            elif p == ECSDI.Precio:
                producto["Precio"] = o
            elif p == ECSDI.Descripcion:
                producto["Descripcion"] = o
            elif p == ECSDI.Id:
                producto["Id"] = o
            elif p == ECSDI.Peso:
                producto["Peso"] = o
            elif p == RDF.type:
                producto["Sujeto"] = s
            listaDeProductos[posicionDeSujetos[s]] = producto
    return render_template('search.html', products=listaDeProductos)

# Función que renderiza los productos comprados
def buy(request):
    global listaDeProductos
    listaDeCompra = []
    for producto in request.form.getlist("checkbox"):
        listaDeCompra.append(listaDeProductos[int(producto)])

    numTarjeta = int(request.form['numeroTarjeta'])
    prioridad = int(request.form['prioridad'])
    direccion = request.form['direccion']
    codigoPostal = int(request.form['codigoPostal'])
    respuestaVenta = procesarVenta(listaDeCompra, prioridad, numTarjeta, direccion, codigoPostal)
    factura = respuestaVenta.value(predicate=RDF.type, object=ECSDI.Factura)
    tarjeta = respuestaVenta.value(subject=factura, predicate=ECSDI.Tarjeta)
    total = respuestaVenta.value(subject=factura, predicate=ECSDI.PrecioTotal)
    productos = respuestaVenta.subjects(object=ECSDI.Producto)
    productosEnFactura = []
    for producto in productos:
        product = [respuestaVenta.value(subject=producto, predicate=ECSDI.Nombre),
                   respuestaVenta.value(subject=producto, predicate=ECSDI.Precio)]
        productosEnFactura.append(product)

    return render_template('ventaRealizada.html', products=productosEnFactura, tarjeta=tarjeta, total=total)

# Función que procesa una venta y la envía el grafo resultado de haber hablado con el agente correspondiente
def procesarVenta(listaDeCompra, prioridad, numTarjeta, direccion, codigoPostal):
    logger.info("Procesando compra")
    grafoCompra = Graph()

    content = ECSDI['PeticionCompra' + str(getMessageCount())]
    grafoCompra.add((content,RDF.type,ECSDI.PeticionCompra))
    grafoCompra.add((content,ECSDI.Prioridad,Literal(prioridad, datatype=XSD.int)))
    grafoCompra.add((content,ECSDI.Tarjeta,Literal(numTarjeta, datatype=XSD.int)))

    sujetoDireccion = ECSDI['Direccion'+ str(getMessageCount())]
    grafoCompra.add((sujetoDireccion,RDF.type,ECSDI.Direccion))
    grafoCompra.add((sujetoDireccion,ECSDI.Direccion,Literal(direccion,datatype=XSD.string)))
    grafoCompra.add((sujetoDireccion,ECSDI.CodigoPostal,Literal(codigoPostal,datatype=XSD.int)))

    sujetoCompra = ECSDI['Compra'+str(getMessageCount())]
    grafoCompra.add((sujetoCompra, RDF.type, ECSDI.Compra))
    grafoCompra.add((sujetoCompra, ECSDI.Destino, URIRef(sujetoDireccion)))


    for producto in listaDeCompra:
        sujetoProducto = producto['Sujeto']
        grafoCompra.add((sujetoProducto, RDF.type, ECSDI.Producto))
        grafoCompra.add((sujetoProducto,ECSDI.Descripcion,producto['Descripcion']))
        grafoCompra.add((sujetoProducto,ECSDI.Nombre,producto['Nombre']))
        grafoCompra.add((sujetoProducto,ECSDI.Precio,producto['Precio']))
        grafoCompra.add((sujetoProducto,ECSDI.Peso,producto['Peso']))
        grafoCompra.add((sujetoCompra, ECSDI.Contiene, URIRef(sujetoProducto)))

    grafoCompra.add((content,ECSDI.De,URIRef(sujetoCompra)))

    vendedor = getAgentInfo(agn.VendedorAgent, DirectoryAgent, UserPersonalAgent,getMessageCount())

    respuestaVenta = send_message(
        build_message(grafoCompra, perf=ACL.request, sender=UserPersonalAgent.uri, receiver=vendedor.uri,
                      msgcnt=getMessageCount(),
                      content=content), vendedor.address)


    return respuestaVenta

# Función que solizita los productos que un usuario con una tarjeta ha comprado y están disponibles para su devolución
def procesarRetorno(request):
    global listaDeProductos
    grafoDeContenido = Graph()
    accion = ECSDI["PeticionProductosEnviados" + str(getMessageCount())]
    grafoDeContenido.add((accion, RDF.type, ECSDI.PeticionProductosEnviados))
    tarjeta = request.form['tarjeta']
    grafoDeContenido.add((accion, ECSDI.Tarjeta, Literal(tarjeta, datatype=XSD.int)))
    agente = getAgentInfo(agn.GestorDeDevoluciones, DirectoryAgent, UserPersonalAgent, getMessageCount())
    # Enviamos petición de filtrado al agente filtrador
    grafoBusqueda = send_message(
        build_message(grafoDeContenido, perf=ACL.request, sender=UserPersonalAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=accion), agente.address)

    listaDeProductos = []
    posicionDeSujetos = {}
    indice = 0
    for s, p, o in grafoBusqueda:
        if s not in posicionDeSujetos:
            posicionDeSujetos[s] = indice
            indice += 1
            listaDeProductos.append({})
        if s in posicionDeSujetos:
            producto = listaDeProductos[posicionDeSujetos[s]]
            if p == ECSDI.Nombre:
                producto["Nombre"] = o
            elif p == ECSDI.Precio:
                producto["Precio"] = o
            elif p == ECSDI.Descripcion:
                producto["Descripcion"] = o
            elif p == ECSDI.Id:
                producto["Id"] = o
            elif p == ECSDI.Peso:
                producto["Peso"] = o
            elif p == RDF.type:
                producto["Sujeto"] = s
            elif p == ECSDI.EsDe:
                producto["Compra"] = o
            listaDeProductos[posicionDeSujetos[s]] = producto
    return render_template('return.html', products=listaDeProductos)

# Función que procesa el retorno de los productos que el usuario ha solicitado para retornar contactando con el agente pertinente
def submitReturn(request):
    global listaDeProductos
    listaDeDevoluciones = []
    for producto in request.form.getlist("checkbox"):
        listaDeDevoluciones.append(listaDeProductos[int(producto)])
    accion = ECSDI["RetornarProductos" + str(getMessageCount())]
    grafoDeContenido = Graph()
    grafoDeContenido.add((accion, RDF.type, ECSDI.RetornarProductos))
    direccion = request.form['direccion']
    codigoPostal = int(request.form['codigoPostal'])

    for producto in listaDeDevoluciones:
        sujetoProducto = producto['Sujeto']
        grafoDeContenido.add((sujetoProducto, RDF.type, ECSDI.ProductoEnviado))
        grafoDeContenido.add((sujetoProducto, ECSDI.Descripcion, producto['Descripcion']))
        grafoDeContenido.add((sujetoProducto, ECSDI.Nombre, producto['Nombre']))
        grafoDeContenido.add((sujetoProducto, ECSDI.Precio, producto['Precio']))
        grafoDeContenido.add((sujetoProducto, ECSDI.Peso, producto['Peso']))
        grafoDeContenido.add((sujetoProducto, ECSDI.EsDe, producto['Compra']))
        grafoDeContenido.add((accion, ECSDI.Auna, URIRef(sujetoProducto)))

    sujetoDireccion = ECSDI['Direccion' + str(getMessageCount())]
    grafoDeContenido.add((sujetoDireccion, RDF.type, ECSDI.Direccion))
    grafoDeContenido.add((sujetoDireccion, ECSDI.Direccion, Literal(direccion, datatype=XSD.string)))
    grafoDeContenido.add((sujetoDireccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
    grafoDeContenido.add((accion, ECSDI.DireccionadoA, URIRef(sujetoDireccion)))
    agente = getAgentInfo(agn.GestorDeDevoluciones, DirectoryAgent, UserPersonalAgent, getMessageCount())

    grafoBusqueda = send_message(
        build_message(grafoDeContenido, perf=ACL.request, sender=UserPersonalAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=accion), agente.address)

    return render_template('procesandoRetorno.html')

#Función que solicita el conjunto de productos recomendables para el usuario al agente pertinente
def pedirRecomendacion():
    sujetoRecomendacion = ECSDI["PeticionRecomendacion" + str(getMessageCount())]
    grafo = Graph();
    grafo.add((sujetoRecomendacion, RDF.type, ECSDI.PeticionRecomendacion))
    agente = getAgentInfo(agn.PromotorDeProductos, DirectoryAgent, UserPersonalAgent, getMessageCount())
    # Enviamos petición de filtrado al agente filtrador
    grafoBusqueda = send_message(
        build_message(grafo, perf=ACL.request, sender=UserPersonalAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=sujetoRecomendacion), agente.address)

    listaDeProductos = []
    posicionDeSujetos = {}
    indice = 0
    for s, p, o in grafoBusqueda:
        if s not in posicionDeSujetos:
            posicionDeSujetos[s] = indice
            indice += 1
            listaDeProductos.append({})
        if s in posicionDeSujetos:
            producto = listaDeProductos[posicionDeSujetos[s]]
            if p == ECSDI.Nombre:
                producto["Nombre"] = o
            elif p == ECSDI.Precio:
                producto["Precio"] = o
            elif p == ECSDI.Descripcion:
                producto["Descripcion"] = o
            elif p == ECSDI.Id:
                producto["Id"] = o
            elif p == ECSDI.Peso:
                producto["Peso"] = o
            elif p == RDF.type:
                producto["Sujeto"] = s
            listaDeProductos[posicionDeSujetos[s]] = producto
    return listaDeProductos

# Función que devuelve la página principal de ECSDIstore
@app.route("/")
def index():

    return render_template('indexAgentePersonal.html',products=pedirRecomendacion())

# Función que atiende a peticiones GET Y POST de busqueda, GET para coger la página que nos permite ver el filtro
# y post para procesar las peticiones de filtrado
@app.route("/search", methods=['GET', 'POST'])
def search():
    global listaDeProductos
    if request.method == 'GET':
        return render_template('search.html', products = None)
    elif request.method == 'POST':
        if request.form['submit'] == 'Search':
            return enviarPeticionBusqueda(request)
        elif request.form['submit'] == 'Buy':
            return buy(request)

# Función que atiende a las peticiones de recomendación
@app.route("/recommend")
def recommend():

    return render_template('showRecommendations.html', products=pedirRecomendacion())

@app.route("/purchased",methods=['GET', 'POST'])
def getProductsToReturn():
    global listaDeProductos
    if request.method == 'POST':
        if request.form['return'] == 'submit':
            return procesarRetorno(request)

        elif request.form['return'] == 'Submit':
            return submitReturn(request)

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
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)
    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=UserPersonalAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=UserPersonalAgent.uri, msgcnt=getMessageCount())
        else:
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)
            if accion == ECSDI.PeticionValoracion :
                productos = grafoEntrada.objects(predicate=ECSDI.Valora)
                grafoValoraciones = Graph()
                accion2 = ECSDI['RespuestaValoracion'+str(getMessageCount())]
                grafoValoraciones.add((accion2,RDF.type,ECSDI.RespuestaValoracion))
                for p in productos:
                    randomNumber = random.randint(0, 5)
                    grafoValoraciones.add((p,RDF.type,ECSDI.Producto))
                    grafoValoraciones.add((p,ECSDI.Valoracion,Literal(randomNumber,datatype=XSD.int)))
                    grafoValoraciones.add((accion2,ECSDI.Valora,URIRef(p)))


                resultadoComunicacion = grafoValoraciones;
    logger.info('Respondemos a la petición de envio')
    serialize = resultadoComunicacion.serialize(format='xml')
    return serialize, 200

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
    gr = register_message()

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = registerAgent(UserPersonalAgent, DirectoryAgent, UserPersonalAgent.uri, getMessageCount())
    return gr

if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1)
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port, debug=False)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
