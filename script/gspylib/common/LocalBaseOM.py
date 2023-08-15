# -*- coding:utf-8 -*-
#############################################################################
# Copyright (c) 2020 Huawei Technologies Co.,Ltd.
#
# openGauss is licensed under Mulan PSL v2.
# You can use this software according to the terms
# and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS,
# WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
#############################################################################
import sys
import os

sys.path.append(sys.path[0] + "/../../")
from gspylib.common.GaussLog import GaussLog
from gspylib.common.DbClusterInfo import dbClusterInfo
from gspylib.common.DbClusterStatus import DbClusterStatus
from gspylib.common.ErrorCode import ErrorCode
from gspylib.component.CM.CM_OLAP.CM_OLAP import CM_OLAP
from gspylib.component.DSS.dss_comp import Dss
from gspylib.component.Kernel.DN_OLAP.DN_OLAP import DN_OLAP
from domain_utils.cluster_file.version_info import VersionInfo
from base_utils.os.net_util import NetUtil
from base_utils.os.user_util import UserUtil
from base_utils.os.env_util import EnvUtil
from gspylib.component.DSS.dss_checker import DssConfig
import impl.upgrade.UpgradeConst as const
 


class LocalBaseOM(object):
    """
    Base class for local command
    """

    def __init__(self,
                 logFile=None,
                 user=None,
                 clusterConf=None,
                 dwsMode=False,
                 initParas=None,
                 gtmInitParas=None,
                 paxos_mode=False,
                 dss_mode=False,
                 dss_config="",
                 dorado_config="",
                 dorado_cluster_mode=""):
        '''
        Constructor
        '''
        if (logFile is not None):
            self.logger = GaussLog(logFile, self.__class__.__name__)
        else:
            self.logger = None
        self.clusterInfo = None
        self.dbNodeInfo = None
        self.clusterConfig = clusterConf
        self.user = user
        self.group = ""
        self.dws_mode = dwsMode
        if initParas is None:
            initParas = []
        self.initParas = initParas
        if gtmInitParas is None:
            gtmInitParas = []
        self.gtmInitParas = gtmInitParas
        self.etcdCons = []
        self.cmCons = []
        self.gtmCons = []
        self.cnCons = []
        self.dnCons = []
        self.gtsCons = []
        self.dss_cons = []
        self.paxos_mode = paxos_mode
        self.dss_mode = dss_mode
        self.dss_config = dss_config
        self.dorado_config = dorado_config
        self.dorado_cluster_mode = dorado_cluster_mode

    def initComponent(self, paxos_mode=False):
        """
        function: Init component
        input : NA
        output: NA
        """
        self.initCmComponent()
        self.initKernelComponent(paxos_mode)
        self.init_dss_component(self.dss_mode)


    def init_dss_component(self, dss_mode=False):
        if not dss_mode:
            return
        for _ in self.dbNodeInfo.datanodes:
            component = Dss()
            component.logger = self.logger
            component.binPath = "%s/bin" % self.clusterInfo.appPath
            component.clusterType = self.clusterInfo.clusterType
            component.dss_mode = dss_mode
            self.dss_cons.append(component)

    def initComponentAttributes(self, component):
        """
        function: Init  component attributes on current node
        input : Object component
        output: NA
        """
        component.logger = self.logger
        component.binPath = "%s/bin" % self.clusterInfo.appPath
        component.dwsMode = self.dws_mode
        component.dss_mode = self.dss_mode
        if self.dss_mode:
            component.dss_config = self.dss_config

    def initCmComponent(self):
        """
        function: Init cm component on current node
        input : Object nodeInfo
        output: NA
        """
        for inst in self.dbNodeInfo.cmservers:
            component = CM_OLAP()
            # init component cluster type
            component.clusterType = self.clusterInfo.clusterType
            component.instInfo = inst
            self.initComponentAttributes(component)
            self.cmCons.append(component)

        for inst in self.dbNodeInfo.cmagents:
            component = CM_OLAP()
            # init component cluster type
            component.clusterType = self.clusterInfo.clusterType
            component.instInfo = inst
            self.initComponentAttributes(component)
            self.cmCons.append(component)

    def initKernelComponent(self, paxos_mode=False):
        """
        function: Init kernel component on current node
        input : Object nodeInfo
        output: NA
        """
        for inst in self.dbNodeInfo.datanodes:
            component = DN_OLAP()
            # init component cluster type
            component.clusterType = self.clusterInfo.clusterType
            component.instInfo = inst
            component.instInfo.peerInstanceInfos = \
                self.clusterInfo.getPeerInstance(component.instInfo)
            component.paxos_mode = paxos_mode
            self.initComponentAttributes(component)
            component.initParas = self.initParas
            component.dorado_config = self.dorado_config
            component.dorado_cluster_mode = self.dorado_cluster_mode
            self.dnCons.append(component)

    def readConfigInfo(self):
        """
        function: Read config from static config file
        input : NA
        output: NA
        """
        try:
            is_dss_mode = EnvUtil.is_dss_mode(self.user)
            self.clusterInfo = dbClusterInfo()
            hostName = NetUtil.GetHostIpOrName()
            dynamicFileExist = False
            if self.__class__.__name__ == "Start":
                dynamicFileExist = \
                    self.clusterInfo.dynamicConfigExists(self.user)
            if dynamicFileExist and not is_dss_mode:
                self.clusterInfo.readDynamicConfig(self.user)
                self.dbNodeInfo = self.clusterInfo.getDbNodeByName(hostName)
            else:
                self.clusterInfo.initFromStaticConfig(self.user)
                self.dbNodeInfo = self.clusterInfo.getDbNodeByName(hostName)
            if self.dbNodeInfo is None:
                self.logger.logExit(ErrorCode.GAUSS_516["GAUSS_51619"] %
                                    hostName)
        except Exception as e:
            self.logger.logExit(str(e))

        self.logger.debug("Instance information on local node:\n%s" %
                          str(self.dbNodeInfo))

    def readConfigInfoByXML(self):
        """
        function: Read config from xml config file
        input : NA
        output: NA
        """
        try:
            if (self.clusterConfig is None):
                self.logger.logExit(ErrorCode.GAUSS_502["GAUSS_50201"] %
                                    "XML configuration file")
            self.clusterInfo = dbClusterInfo()
            self.clusterInfo.initFromXml(self.clusterConfig)
            hostName = NetUtil.GetHostIpOrName()
            self.dbNodeInfo = self.clusterInfo.getDbNodeByName(hostName)
            if (self.dbNodeInfo is None):
                self.logger.logExit(ErrorCode.GAUSS_516["GAUSS_51619"] %
                                    hostName)
        except Exception as e:
            self.logger.logExit(str(e))
        self.logger.debug("Instance information on local node:\n%s" %
                          str(self.dbNodeInfo))

    def getUserInfo(self):
        """
        Get user and group
        """
        if os.path.islink(self.clusterInfo.appPath):
            appPath = os.path.realpath(self.clusterInfo.appPath)
        elif os.path.exists(self.clusterInfo.appPath):
            appPath = self.clusterInfo.appPath
        else:
            commitid = VersionInfo.getCommitid()
            appPath = self.clusterInfo.appPath + "_" + commitid
        self.logger.debug("Get the install path %s user info." % appPath)
        (self.user, self.group) = UserUtil.getPathOwner(appPath)
        if (self.user == "" or self.group == ""):
            self.logger.logExit(ErrorCode.GAUSS_503["GAUSS_50308"])
