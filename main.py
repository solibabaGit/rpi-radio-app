import subprocess as sp
import time
import wx
import threading as th
import struct as st
import numpy as np
import skimage.draw as skd
#import matplotlib.pyplot as plt

class MediaCenter(wx.Frame):
    def __init__(self, parent, title): 
        super(MediaCenter, self).__init__(parent, title = title,size = (480,320))  
        self.ShowFullScreen(wx.FULLSCREEN_ALL)
        self.Bind(wx.EVT_PAINT, self.OnPaint) 
        self.Centre()
        self.canvasWidth = 480
        self.canvasHeight = 320
        self.bgColor = "black"
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self.UI_BLUETOOTH = 1
        self.UI_TEMP_HIST = 3
        self.UI_RADIO = 2
        self.UI_RADIOOVERVIEW = 4
        self.uiMode = self.UI_RADIO #UI_BLUETOOTH
        self.prevMainUiState = self.UI_RADIO
        self.clearAll = True
        self.lastDragEvent = None
        self.lastClickEvent = None
        self.LMB_DOWN = False
        self.UIImages = [wx.Bitmap("bluetoothicon_black_small.png"),wx.Bitmap("radioicon_small.png"),wx.Bitmap("list_icon.png"),wx.Bitmap("temp_icon_small.png")]
        self.UIImages_posY = np.cumsum(np.array([self.UIImages[i].GetHeight() for i in range(len(self.UIImages))]))
        self.triangle_left = wx.Bitmap("triangle_left.png")
        
        self.BLUETOOTH = 1
        self.RADIO = 2
        self.mode = self.BLUETOOTH
        self.radioProc = None
        self.parseRadios()
        self.curRadioListIndex = 0
        self.sortRadioListAlphabetically = False
        self.numChannelsPerRow = 2
        self.numChannelsPerCol = 3
        self.radioListCurPage = 0
        self.radioImages = [wx.Bitmap(ri) for ri in self.radioImages]
        for i in range(len(self.radioImages)):
            tempImage = wx.ImageFromBitmap(self.radioImages[i])
            sf = min(self.canvasWidth*0.8/self.radioImages[i].GetWidth(), self.canvasHeight*0.6/self.radioImages[i].GetHeight())
            tempImage = tempImage.Scale((int)(self.radioImages[i].GetWidth()*sf),(int)(self.radioImages[i].GetHeight()*sf),wx.IMAGE_QUALITY_HIGH)
            self.radioImages[i] = wx.BitmapFromImage(tempImage)
        self.curURLindex = 0
        self.bluetoothTextData = ["OFF","white"]
        self.temperatureText = "NaN °C"
        self.temperatureTextSize = wx.Size(10,10)
        self.timeText = ""
        
        self.restoreVolume()
        
        # start threads:
        self.myEVT_COUNT = wx.NewEventType()
        self.EVT_COUNT = wx.PyEventBinder(self.myEVT_COUNT, 1)
        
        self.tempReadoutThread = th.Thread(target=self.readout_temperature)
        self.tempReadoutThread.start()
        
        self.btReadoutThread = th.Thread(target=self.readout_bluetooth_state)
        self.btReadoutThread.start()
        
        self.clockThread = th.Thread(target=self.change_clock)
        self.clockThread.start()
        
        self.Bind(wx.EVT_LEFT_DOWN, self.clicked)
        self.Bind(wx.EVT_LEFT_UP, self.released) 
        self.Bind(wx.EVT_MOTION, self.moved) 
        
        #self.canvas.bind("<B1-Motion>", self.moved)
        #self.canvas.bind("<Button-1>", self.clicked)
        #self.canvas.bind("<ButtonRelease-1>", self.released)
        
        '''proc = sp.Popen(['/usr/bin/vlc','-I','dummy','--open','https://liveradio.swr.de/sw331ch/swr3/play.aac'])
        proc.terminate()'''

    def parseRadios(self):
        f = open("radios.txt")
        line = f.readline()
        self.radioURLs = []
        self.radioImages = []
        self.radioNames = []
        while(line != ""):
            line = line[:-1].split(";")
            self.radioURLs.append(line[0])
            self.radioImages.append(line[1])
            self.radioNames.append(line[2])
            line = f.readline()
        print(self.radioURLs)
        print(self.radioImages)

    def readout_temperature(self):
        while(True):
            # readout temperature from GPIO attached sensor every 2 seconds:
            f = open("/sys/bus/w1/devices/28-00000809d450/w1_slave","r")
            line1 = f.readline()
            line2 = f.readline()    
            f.close()
            temperature = "NaN"
            if line2[-4:-1] != "YES" and line1 != line2:
                line2split = line2.split("=")
                if len(line2split) > 1:
                    temperature = float(line2split[1].replace("\n",""))/1000.
                    lt = time.localtime()
                    ct = time.time()
                    f = open(time.strftime("%d-%m-%Y.binary",lt),"a+b")
                    f.write(st.pack("d",ct))
                    f.write(st.pack("d",temperature))
                    f.close()
            if temperature != "NaN":
                newTemperatureText = str(np.round(temperature,1))+" °C"
                if self.temperatureText != newTemperatureText or self.uiMode == self.UI_TEMP_HIST:
                    self.temperatureText = newTemperatureText
                    wx.CallAfter(self.Refresh)
            
            time.sleep(2)
            
    def readout_bluetooth_state(self):
        while(True):
            # readout bluetooth power state every 2 seconds:
            powered = self.callBTMGMT()
            redraw = False
            if powered:
                if self.bluetoothTextData[0] == "OFF":
                    redraw = True
                self.bluetoothTextData[0] = "ON"
                self.bluetoothTextData[1] = "blue"
            else:
                if self.bluetoothTextData[0] == "ON":
                    redraw = True
                self.bluetoothTextData[0] = "OFF"
                self.bluetoothTextData[1] = "white"
            if redraw:
                wx.CallAfter(self.Refresh)
            
            time.sleep(2)
            
    def change_clock(self):
        while(True):
            lt = time.localtime()
            newTimeText = time.strftime("%H:%M",time.localtime())
            if newTimeText != self.timeText:
                self.timeText = newTimeText
                wx.CallAfter(self.Refresh)
                
            time.sleep(1)
            
    def callBTMGMT(self):
        proc = sp.Popen(['/bin/btmgmt','info'],stdout=sp.PIPE, stderr=sp.PIPE)
        try:
            outs, errs = proc.communicate(timeout=1)
        except sp.TimeoutExpired:
            proc.kill()
            outs, errs = proc.communicate()
        proc.kill()
        outs = str(outs).replace("\\t","").split("\\n")
        for o in outs:
            o = o.split(":")
            if o[0] == "current settings":
                cs = o[1].split(" ")
                for csi in cs:
                    if csi == "powered":
                        return True
        return False

    def powerBT(self,powerstate):
        proc = sp.Popen(['/bin/sudo','btmgmt','power',powerstate])
        
    def switchToMode(self,newMode):
        if newMode == self.BLUETOOTH:
            self.stopRadio()
            powered = self.callBTMGMT()
            if not powered:
                self.powerBT("on")
            proc = sp.Popen(['/bin/sudo','btmgmt','discov','yes'])
            self.bluetoothTextData[0] = "ON"
            self.bluetoothTextData[1] = "blue"
            self.mode = newMode
        elif newMode == self.RADIO:
            powered = self.callBTMGMT()
            if powered:
                proc = sp.Popen(['/bin/sudo','btmgmt','con'],stdout=sp.PIPE, stderr=sp.PIPE)
                try:
                    outs, errs = proc.communicate(timeout=1)
                except sp.TimeoutExpired:
                    proc.kill()
                    outs, errs = proc.communicate()
                proc.kill()
                if outs is not None:
                    outs = str(outs).replace("\\t","").split("\\n")
                    o = outs[0].split(" ")
                    deviceID = o[0]
                    proc = sp.Popen(['/bin/sudo','btmgmt','disconnect',deviceID])
                    
                proc = sp.Popen(['/bin/sudo','btmgmt','discov','no'])
                self.powerBT("off")
            self.bluetoothTextData[0] = "OFF"
            self.bluetoothTextData[1] = "white"
            self.startRadio()
            self.mode = newMode
            
    def startRadio(self):
        self.radioProc = sp.Popen(['/usr/bin/vlc','-I','dummy','--open',self.radioURLs[self.curURLindex]])
        
    def stopRadio(self):
        if self.radioProc is not None:
            self.radioProc.terminate()
            
    def restoreVolume(self):
        f = open("volume.txt","r")
        try:
            line = f.readline()
            print("----")
            print(line)
            print("----")
            print(int(float(line)))
            print("....")
            self.volume = int(float(line))
            self.changeVolume(self.volume)
        except:
            self.changeVolume(100)
            self.saveVolume()
        f.close()
        
    def saveVolume(self):
        f = open("volume.txt","w")
        f.write(str(self.volume))
        f.flush()
        f.close()
            
    def changeVolume(self,newVolumePercent):
        if newVolumePercent > 100 or newVolumePercent < 0:
            return
        self.volume = newVolumePercent
        self.saveVolume()
        volumeAMIXER = int(np.log(1 + newVolumePercent)/np.log(101) * 100)
        proc = sp.Popen(['/usr/bin/amixer','set','Master',str(self.volume)+'%'])
        try:
            outs, errs = proc.communicate(timeout=10)
        except sp.TimeoutExpired:
            proc.kill()
            outs, errs = proc.communicate()
        proc.kill()        
    
    def redrawStatusbar(self,dc,bt=True,clock=True,temp=True):
        if bt:
            dc.SetTextForeground(self.bluetoothTextData[1])
            dc.DrawText(self.bluetoothTextData[0],0,0)
        if clock:
            dc.SetTextForeground(wx.Colour(255,255,255))
            self.timeText = time.strftime("%H:%M",time.localtime())
            w, h = dc.GetTextExtent(self.timeText)
            dc.DrawText(self.timeText,int((self.canvasWidth - w)/2.),0)
        if temp:
            dc.SetTextForeground(wx.Colour(255,255,255))
            w, h = dc.GetTextExtent(self.temperatureText)
            self.temperatureTextSize = wx.Size(w,h)
            dc.DrawText(self.temperatureText,int(self.canvasWidth - w),0)
    
    def redrawVolumeStatus(self,dc):
        volColor = wx.Colour(255,0,0)
        if self.volume > 66:
            volColor = wx.Colour(255,0,255)
        elif self.volume > 33:
            volColor = wx.Colour(255,255,0)
        b = wx.Brush(volColor) 
        dc.SetBrush(b)
        dc.DrawRectangle(0,self.canvasHeight - 70,int(self.canvasWidth/100.*self.volume),70)
        
    def OnPaint(self,e):
        dc = wx.BufferedPaintDC(self)#PaintDC(self) 
        brush = wx.Brush(self.bgColor)  
        dc.SetBackground(brush) 
        dc.Clear()
        
        font = wx.Font(25, wx.ROMAN, wx.ITALIC, wx.NORMAL) 
        dc.SetFont(font) 
        dc.SetTextForeground(wx.Colour(255,255,255)) 
        w, h = dc.GetTextExtent("TEST")
        
        '''color = wx.Colour(255,0,0)
        b = wx.Brush(color) 
        dc.SetBrush(b) 
        dc.DrawCircle(300,125,50) 
        dc.SetBrush(wx.Brush(wx.Colour(255,255,255))) 
        dc.DrawCircle(300,125,30) '''
        
        dc.DrawBitmap(self.UIImages[0],0,self.canvasHeight*0.25)
        dc.DrawBitmap(self.UIImages[1],0,self.canvasHeight*0.25+self.UIImages_posY[0])
        dc.DrawBitmap(self.UIImages[2],0,self.canvasHeight*0.25+self.UIImages_posY[1])
        dc.DrawBitmap(self.UIImages[3],0,self.canvasHeight*0.25+self.UIImages_posY[2])
        
        self.redrawStatusbar(dc)
        if self.uiMode == self.UI_BLUETOOTH:
            dc.DrawBitmap(self.triangle_left,self.UIImages[0].GetWidth()+2,self.canvasHeight*0.25 + (self.UIImages[0].GetHeight() - self.triangle_left.GetHeight())/2.)
            self.redrawVolumeStatus(dc)
        elif self.uiMode == self.UI_RADIO:
            dc.DrawBitmap(self.triangle_left,self.UIImages[0].GetWidth()+2,self.canvasHeight*0.25 + self.UIImages_posY[0] + (self.UIImages[1].GetHeight() - self.triangle_left.GetHeight())/2.)
            dc.DrawBitmap(self.radioImages[self.curURLindex],self.canvasWidth*0.15 +  (self.canvasWidth*0.85 - self.radioImages[self.curURLindex].GetWidth())/2.,self.canvasHeight*0.2 + (self.canvasHeight*0.6 - self.radioImages[self.curURLindex].GetHeight())/2.,True) 
            self.redrawVolumeStatus(dc)
        elif self.uiMode == self.UI_RADIOOVERVIEW:
            dc.DrawBitmap(self.triangle_left,self.UIImages[0].GetWidth()+2,self.canvasHeight*0.25 + self.UIImages_posY[1] + (self.UIImages[2].GetHeight() - self.triangle_left.GetHeight())/2.)
            self.drawRadioList(dc)
        elif self.uiMode == self.UI_TEMP_HIST:
            dc.DrawBitmap(self.triangle_left,self.UIImages[0].GetWidth()+2,self.canvasHeight*0.25 + self.UIImages_posY[2] + (self.UIImages[3].GetHeight() - self.triangle_left.GetHeight())/2.)
            self.renderTempHistory(dc)
            
    def drawRadioList(self,dc):
        # draw current list state
        tempRadioList = self.radioNames
        tempsortedIndexToGlobalIndex = range(len(self.radioNames))
        if self.sortRadioListAlphabetically:
            pass
        for i in range(self.numChannelsPerRow):
            for j in range(self.numChannelsPerCol):
                curIndex = self.numChannelsPerCol*i + j + self.radioListCurPage*self.numChannelsPerCol*self.numChannelsPerRow
                if curIndex < len(tempRadioList):
                    dc.DrawText(tempRadioList[curIndex],self.canvasWidth*0.15 + self.canvasWidth*(0.8/self.numChannelsPerRow)*i,self.canvasHeight*0.2 + self.canvasHeight*(0.6/self.numChannelsPerCol)*j)
        
    def renderTempHistory(self,dc):
        t1 = time.time()
        data = np.fromfile(time.strftime("%d-%m-%Y.binary",time.localtime()),dtype=np.float64)
        times = data[::2]
        temps = data[1::2]
        
        timeStart = times[0]
        timeEnd = times[-1]
        
        times -= times[0]
        timesRange = times[-1] - times[0]
        minTemp = np.min(temps)
        maxTemp = np.max(temps)
        temps -= minTemp
        
        hexString = 'FFFFFFFF'
        dec = int(hexString, 16)
        rgbaData = np.ones((self.canvasWidth*self.canvasHeight),dtype=np.int32)
        #indicesX = np.array(times/timesRange * (self.canvasWidth - 1),dtype=np.int32)
        #indicesY = np.array((1 - temps/np.max(temps)) * (0.6*self.canvasHeight) + 0.2*self.canvasHeight,dtype=np.int32)
        
        x = times/timesRange * (self.canvasWidth*0.8) + self.canvasWidth*0.19
        y = (1 - temps/np.max(temps)) * (0.6*self.canvasHeight) + 0.2*self.canvasHeight
        #indicesX = np.linspace(0,self.canvasWidth-1,(int)(self.canvasWidth*self.canvasHeight*0.8)) # np.arange(0,self.canvasWidth - 1)
        #indicesY = np.interp(indicesX,x,y)
        
        dx = np.diff(x)
        dy = np.diff(y)
        numPixelPerLine = np.array(np.sqrt(dx**2 + dy**2),dtype=np.int32)
        repX = np.repeat(x[:-1],numPixelPerLine)
        repY = np.repeat(y[:-1],numPixelPerLine)
        #steps = np.concatenate([np.arange(nppl)/nppl for nppl in numPixelPerLine])
        steps = (np.arange(len(repX)) - np.repeat(np.cumsum(numPixelPerLine) - numPixelPerLine[0],numPixelPerLine))/np.repeat(numPixelPerLine,numPixelPerLine) + 1#(np.arange(len(repX)) - np.repeat(np.cumsum(numPixelPerLine) - numPixelPerLine[0],numPixelPerLine))/np.repeat(numPixelPerLine,numPixelPerLine)
        
        repdX = np.repeat(dx,numPixelPerLine)
        repdY = np.repeat(dy,numPixelPerLine)
        
        indicesX = repX + steps*repdX
        indicesY = repY + steps*repdY
        indicesX = np.array(indicesX,dtype=np.int32)
        indicesY = np.array(indicesY,dtype=np.int32)
        
        indices = indicesY * self.canvasWidth + indicesX
        ##indicesYP1 = (indicesY+1) * self.canvasWidth + indicesX
        ##indicesYP1 = np.where(indicesYP1 < self.canvasWidth*self.canvasHeight, indicesYP1, 0)
        ##indicesXP1 = indicesY * self.canvasWidth + indicesX + 1
        ##indicesXP1 = np.where(indicesXP1 < self.canvasWidth*self.canvasHeight, indicesXP1, 0)
        ##indicesXYP1 = (indicesY+1) * self.canvasWidth + indicesX + 1
        ##indicesXYP1 = np.where(indicesXYP1 < self.canvasWidth*self.canvasHeight, indicesXYP1, 0)
        
        rgbaData[indices] *= dec
        
        ##rgbaData[indicesXP1] *= dec
        ##rgbaData[indicesYP1] *= dec
        ##rgbaData[indicesXYP1] *= dec
        bitmap = wx.Bitmap.FromBufferRGBA(self.canvasWidth,self.canvasHeight,rgbaData)
        #print(bitmap.GetData())
        dc.DrawBitmap(bitmap,0,0,True) 
        
        font = wx.Font(12, wx.ROMAN, wx.ITALIC, wx.NORMAL) 
        dc.SetFont(font) 
        dc.DrawText(str(np.round(maxTemp,1)),40,self.canvasHeight*0.2)
        dc.DrawText(str(np.round(minTemp,1)),40,self.canvasHeight*0.8)
        
        dc.DrawText(time.strftime("%H:%M",time.localtime(timeStart)),40,self.canvasHeight*0.85)
        dc.DrawText(time.strftime("%H:%M",time.localtime(timeEnd)),self.canvasWidth*0.9,self.canvasHeight*0.85)
        
        font = wx.Font(25, wx.ROMAN, wx.ITALIC, wx.NORMAL) 
        dc.SetFont(font) 
        
        #maxTemp = np.max(temps)
        #y = temps/maxTemp*(self.canvasHeight*0.6) + 0.2*self.canvasHeight
        
        #x = times/timesRange * self.canvasWidth
        
        #x = np.array(x,dtype=np.int32)
        #y = np.array(y,dtype=np.int32)
        #pen = wx.Pen(wx.Colour(255,255,255))  
        #dc.SetPen(pen)
        #self.pointList = np.zeros((len(x)-1,4),dtype=np.int32)
        #self.pointList[:,0] = x[:-1]
        #self.pointList[:,1] = y[:-1]
        #self.pointList[:,2] = x[1:]
        #self.pointList[:,3] = y[1:]
        #dc.DrawLineList(self.pointList)
        #self.pointList = np.zeros((len(x),2),dtype=np.int32)
        #self.pointList[:,0] = x[:]
        #self.pointList[:,1] = y[:]
        #dc.DrawPointList(self.pointList)
        #for i in range(len(times)-1):
        #    dc.DrawLine(int(x[i]),int(y[i]),int(x[i+1]),int(y[i+1]))
        print("hist draw",time.time() - t1)
        
    def clicked(self,e):
        # react on mouse click events on the canvas
        print("clicked",e)
        self.LMB_DOWN = True
        if self.lastDragEvent is None:
            self.lastDragEvent  = [time.time(),e.GetPosition().x,e.GetPosition().y]
        if self.lastClickEvent is None:
            self.lastClickEvent = [time.time(),e.GetPosition().x,e.GetPosition().y]
        self.lastDragEvent[0] = time.time()
        self.lastDragEvent[1] = e.GetPosition().x
        self.lastDragEvent[2] = e.GetPosition().y
        self.lastClickEvent[0] = time.time()
        self.lastClickEvent[1] = e.GetPosition().x
        self.lastClickEvent[2] = e.GetPosition().y
        print(self.lastDragEvent[1],"y= ",self.lastDragEvent[2])
        
        if self.uiMode == self.UI_BLUETOOTH:
            if e.GetPosition().x > self.canvasWidth - self.temperatureTextSize.GetWidth() and e.GetPosition().y < self.temperatureTextSize.GetHeight():
                print("two temphist")
                self.prevMainUiState = self.uiMode
                self.uiMode = self.UI_TEMP_HIST
                
        elif self.uiMode == self.UI_RADIO:
            if e.GetPosition().x > self.canvasWidth - self.temperatureTextSize.GetWidth() and e.GetPosition().y < self.temperatureTextSize.GetHeight():
                print("to temphist")
                self.prevMainUiState = self.uiMode
                self.uiMode = self.UI_TEMP_HIST
                
        elif self.uiMode == self.UI_RADIOOVERVIEW:
            if e.GetPosition().x > self.canvasWidth - self.temperatureTextSize.GetWidth() and e.GetPosition().y < self.temperatureTextSize.GetHeight():
                print("to temphist")
                self.prevMainUiState = self.uiMode
                self.uiMode = self.UI_TEMP_HIST
                
        elif self.uiMode == self.UI_TEMP_HIST:
            if e.GetPosition().x > self.canvasWidth - self.temperatureTextSize.GetWidth() and e.GetPosition().y < self.temperatureTextSize.GetHeight():
                print("back to prevUiState")
                self.uiMode = self.prevMainUiState
        self.Refresh()
        
    def moved(self,e):
        print("mov",e,"lol",e.LeftDown(),"getbuttoin",e.GetButton(),"cc",e.GetClickCount())
        newDragEvent = [time.time(),e.GetPosition().x,e.GetPosition().y]
        if self.lastDragEvent is None:
            self.lastDragEvent = newDragEvent
            return
        dt = newDragEvent[0] - self.lastDragEvent[0]
        print("dt",dt,"x",e.GetPosition().x - self.lastDragEvent[1],"y",e.GetPosition().y - self.lastDragEvent[2])
        if dt > 1:
            self.lastDragEvent = newDragEvent
            return
        if not self.LMB_DOWN:
            return
        # react on mouse drag events on the canvas
        self.swipeTriggerLength = 50
        if self.uiMode == self.UI_BLUETOOTH:
            if (e.GetPosition().y - self.lastDragEvent[2]) > self.swipeTriggerLength: # swiped down
                pass
            elif (e.GetPosition().y - self.lastDragEvent[2]) < -self.swipeTriggerLength: # swiped up
                print("switch to Radio")
                self.uiMode = self.UI_RADIO
                self.switchToMode(self.RADIO)
                self.LMB_DOWN = False
                self.Refresh()
                
        elif self.uiMode == self.UI_RADIO:
            if (e.GetPosition().y - self.lastDragEvent[2]) > self.swipeTriggerLength: # swiped down
                self.uiMode = self.UI_BLUETOOTH
                self.switchToMode(self.BLUETOOTH)
                self.LMB_DOWN = False
                print("switch to overview")
                self.Refresh()
            elif (e.GetPosition().y - self.lastDragEvent[2]) < -self.swipeTriggerLength: # swiped up
                self.prevMainUiState = self.uiMode
                self.uiMode = self.UI_RADIOOVERVIEW
                
            elif (e.GetPosition().x - self.lastDragEvent[1]) > self.swipeTriggerLength: # swiped right
                self.curURLindex = (self.curURLindex - 1) % len(self.radioURLs)
                self.stopRadio()
                self.startRadio()
                self.LMB_DOWN = False
                print("previous station")
                self.Refresh()
            elif (e.GetPosition().x - self.lastDragEvent[1]) < -self.swipeTriggerLength: # swiped left
                self.curURLindex = (self.curURLindex + 1) % len(self.radioURLs)
                self.stopRadio()
                self.startRadio()
                self.LMB_DOWN = False
                print("next station")
                self.Refresh()
                
        elif self.uiMode == self.UI_RADIOOVERVIEW:
            if (e.GetPosition().y - self.lastDragEvent[2]) > self.swipeTriggerLength: # swiped down
                self.uiMode = self.UI_RADIO
                self.LMB_DOWN = False
                self.Refresh()
            elif (e.GetPosition().y - self.lastDragEvent[2]) < -self.swipeTriggerLength: # swiped up
                self.prevMainUiState = self.uiMode
                self.uiMode = self.UI_TEMP_HIST
                
            elif (e.GetPosition().x - self.lastDragEvent[1]) > self.swipeTriggerLength: # swiped right
                self.radioListCurPage = (self.radioListCurPage + 1) % ((int)(np.ceil(len(self.radioNames)/(self.numChannelsPerCol*self.numChannelsPerRow))))
                self.LMB_DOWN = False
                self.Refresh()
            elif (e.GetPosition().x - self.lastDragEvent[1]) < -self.swipeTriggerLength: # swiped left
                self.radioListCurPage = (self.radioListCurPage - 1) % ((int)(np.ceil(len(self.radioNames)/(self.numChannelsPerCol*self.numChannelsPerRow))))
                self.LMB_DOWN = False
                self.Refresh()
                
        elif self.uiMode == self.UI_TEMP_HIST:
            if (e.GetPosition().y - self.lastDragEvent[2]) > self.swipeTriggerLength: # swiped down
                self.uiMode = self.UI_RADIOOVERVIEW
                self.switchToMode(self.RADIO)
                print("switch to radio")
                self.LMB_DOWN = False
                self.Refresh()
            elif (e.GetPosition().y - self.lastDragEvent[2]) < -self.swipeTriggerLength: # swiped up
                pass
        self.lastDragEvent = newDragEvent
        
    def released(self,e):
        print("rel",e)
        self.LMB_DOWN = False
        self.lastDragEvent = [time.time(),e.GetPosition().x,e.GetPosition().y]
        
        if self.uiMode == self.UI_BLUETOOTH:
            if e.GetPosition().y > self.canvasHeight - 70:
                self.changeVolume(e.GetPosition().x/self.canvasWidth * 100)
                
        elif self.uiMode == self.UI_RADIO:
            if e.GetPosition().y > self.canvasHeight - 70:
                self.changeVolume(e.GetPosition().x/self.canvasWidth * 100)
                
        elif self.uiMode == self.UI_RADIOOVERVIEW:
            if e.GetPosition().x == self.lastClickEvent[1] and e.GetPosition().y == self.lastClickEvent[2]:
                for i in range(self.numChannelsPerRow):
                    for j in range(self.numChannelsPerCol):
                        curIndex = self.numChannelsPerCol*i + j
                        if curIndex < len(self.radioNames):
                            if e.GetPosition().x > self.canvasWidth*0.15 + self.canvasWidth*(0.8/self.numChannelsPerRow)*i and e.GetPosition().x <= self.canvasWidth*0.15 + self.canvasWidth*(0.8/self.numChannelsPerRow)*(i+1) and e.GetPosition().y > self.canvasHeight*0.2 + self.canvasHeight*(0.6/self.numChannelsPerCol)*j and e.GetPosition().y < self.canvasHeight*0.2 + self.canvasHeight*(0.6/self.numChannelsPerCol)*(j+1):
                                self.curURLindex = (curIndex) % len(self.radioURLs)
                                self.stopRadio()
                                self.startRadio()
                                self.uiMode = self.UI_RADIO
        self.Refresh()

if __name__ == "__main__":
    ex = wx.App()
    mc = MediaCenter(None,"MediaCenter")
    ex.MainLoop()
