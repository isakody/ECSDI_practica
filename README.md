# ECSDI_practica

## Introduction *in English*
Assigment for ECSDI in FIB, UPC. A distributed shop system.\
By Núria Bruch Tàrrega, Isabel Codina García and Borja Fernández Ruizdelgado.\
*This assignment is in Spanish.*

- Instructions on how to run the shop can be found below.
- The first and second reports of the assignment are called __ECSDI_Practica_EntregaX_BruchCodinaFernandez.pdf__.
- ~~The final report of the assignment is called __ECSDI_Practica_EntregaFinal_BruchCodinaFernandez.pdf__.~~
- Prometheus diagrams are shown in the reports but can also be found in the file called __ECSDIShop/Prometheus/e-shop.pd__.
- The ontologies described in Protégé can be found in the file called __ECSDIShop/Protege/ECSDIstore.owl__.
- The agents can be found in the directory called __ECSDIShop/agents__.
- The databases are located in the directory called __ECSDIShop/data__.

## Introducción
Práctica de ECSDI en la FIB, UPC. Una tienda distribuida. \
Por Núria Bruch Tàrrega, Isabel Codina García and Borja Fernández Ruizdelgado.

- Las instrucciones de como arrancar la tienda se encuentran más adelante.
- La primera y segunda entrega de la documentación se llaman __ECSDI_Practica_EntregaX_BruchCodinaFernandez.pdf__.
- ~~La entrega final de la documentación se llama __ECSDI_Practica_EntregaFinal_BruchCodinaFernandez.pdf__.~~
- Los diagramas de Prometheus están añadidos en la documentación pero se pueden encontrar en el fichero llamado __ECSDIShop/Prometheus/e-shop.pd__.
- Las ontologías descritas en Protégé se pueden encontrar en el fichero llamado __ECSDIShop/Protege/ECSDIstore.owl__.
- Los agentes se encuentran en el directorio llamado __ECSDIShop/agents__.
- Las bases de datos están en el directorio llamado __ECSDIShop/data__.


## Instrucciones para arrancar los agentes:
#### 1) Arrancar SimpleDirectoryService
#### 2) Arrancar TransportistaDirectoryService y CentroLogisticoDirectoryService
#### 3) Arrancar el resto de agentes

## Juegos de pruebas:

#### 1) Busqueda de productos:

  1) Buscar sin filtro -> Retrona todos los productos de la base de datos.
  2) Buscar por nombre = Cable -> Retorna un producto llamado Cable.
  3) Buscar por precio máximo = 100 -> Retorna los poroductos con un precio inferior a 100.
  4) Buscar por precio mínimo = 100 -> Retorn a los productos con un precio superior a 100.
  5) Bucar por precio máximo = 100 y mínimo = 100 y nombre = Cable -> Retorna el producto Cable.
  
#### 2) Compra:

  1) Compra de Auriculares con CodigoPostal = 8028 -> Factura correcta y atendido por CentroLogístico Nº 1.
  2 Compra de Auriculares con CodigoPostal = 1 -> Factura correcta y atendido por CentroLogístico Nº 2.
  3) Compra de un producto cualquiera y Cable con CodigoPostal = 8028 -> Factura correcta y Cable gestionado por CentroLogístico Nº 2 y el otro producto por el CentroLogístico Nº 1 ya que el 1 no tiene cable
  4) Compra de Barco con prioridad 2 -> Ver que tarda dos turnos en enviar el producto el centro logístico.
  5) Comprar producto de poco peso  cuando los centros logístico no tienen nada pendiente de envío -> Ver que el transportista seleccionado es el Transportista Nº 1.
  6) Cmprar proucto de mucho peso cuando los centros logísticos no tienen nada pendiente de envío -> Ver que el transportista seleccionado es el Transportista Nº 2.
  
 #### 3) Ver Productos recomendados:
 
  1) Recargar varias veces la página y ver que los productos recomendados no son los mismos.
  
 #### 4) Devolver productos:
 
  1) Rellenar formulario con la tarjeta con la que previamente se han hecho compras.
  2) Devolver un producto cualquiera rellendando el formulario -> Observar que el transportista prefijado pra devoluciones contesta y tiene la dirección correspondiente
  3) Modificar la DB la fecha de entrega de los envíos para ver que efectivamente solo se muestran los productos comprados en un periodo de 14 días despúes de recibir la entrega.
  
 #### 5) Recomendaciones:
 
  1) Ver base de datos antes de realizar cualquier compra y ver que esta está vacía, mirar después de la demo y observar que esta ha sido rellenada con los productos comprados por el usuario y han sido valorados de manera aleatoria por el agente que representa al usuario.
