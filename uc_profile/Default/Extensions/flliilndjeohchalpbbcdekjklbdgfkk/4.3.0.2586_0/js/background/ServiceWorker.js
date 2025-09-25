/*!
 * © 2016 Avira Operations GmbH & Co. KG. All rights reserved.
 * No part of this extension may be reproduced, stored or transmitted in any
 * form, for any reason or by any means, without the prior permission in writing
 * from the copyright owner. The text, layout, and designs presented are
 * protected by the copyright laws of the United States and international
 * treaties.
 */
!function r(e,t,o){function i(u,c){if(!t[u]){if(!e[u]){var s="function"==typeof require&&require;if(!c&&s)return s(u,!0);if(n)return n(u,!0);var p=new Error("Cannot find module '"+u+"'");throw p.code="MODULE_NOT_FOUND",p}var f=t[u]={exports:{}};e[u][0].call(f.exports,(function(r){return i(e[u][1][r]||r)}),f,f.exports,r,e,t,o)}return t[u].exports}for(var n="function"==typeof require&&require,u=0;u<o.length;u++)i(o[u]);return i}({1:[function(r,e,t){"use strict";(new class{importBGScripts(){try{importScripts("background.js"),importScripts("../webRequestListenerWrapper.js")}catch(r){console.debug(`ServiceWorker failed to load one of the bg scripts due to , ${r}`)}}}).importBGScripts()},{}]},{},[1]);