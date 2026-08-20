# -*- coding: utf-8 -*-
"""Normalizacion de la respuesta del modelo (IA._clean).

El modelo a veces devuelve la secuencia literal "\\n" (barra invertida + n)
en lugar de un salto de linea real, y asi acababa impresa dentro del
documento generado.
"""
import pytest

IA = pytest.importorskip('IA')

# Barra invertida literal, para no depender del escapado del fichero
BS = chr(92)


def test_convierte_backslash_n_en_salto_real():
    entrada = 'trilema de la blockchain.' + BS + 'nPara comenzar, se analizara'
    salida = IA._clean(entrada)
    assert BS + 'n' not in salida
    assert salida == 'trilema de la blockchain.\nPara comenzar, se analizara'


def test_convierte_doble_backslash_n():
    entrada = 'integridad de la red.' + BS + 'n' + BS + 'nPor un lado'
    salida = IA._clean(entrada)
    assert BS + 'n' not in salida
    assert salida == 'integridad de la red.\n\nPor un lado'


def test_convierte_crlf_literal_en_un_solo_salto():
    entrada = 'linea uno' + BS + 'r' + BS + 'nlinea dos'
    assert IA._clean(entrada) == 'linea uno\nlinea dos'


def test_quita_prefijo_output_heredado():
    assert IA._clean('output: Texto') == 'Texto'


def test_respeta_saltos_reales():
    assert IA._clean('Un salto real\nde verdad') == 'Un salto real\nde verdad'


def test_texto_vacio():
    assert IA._clean('') == ''
    assert IA._clean(None) == ''
