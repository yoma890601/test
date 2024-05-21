import os
import argparse

import glob
import trimesh
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.models import Sequential
from matplotlib import pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import KFold
from sklearn.metrics import confusion_matrix
from sklearn.utils.multiclass import unique_labels
from tensorflow.keras.layers import Dense, Conv1D, BatchNormalization


# vram=1024*3
# gpus = tf.config.experimental.list_physical_devices('GPU')
# if gpus:
#   try:
#     tf.config.experimental.set_virtual_device_configuration(gpus[0], [tf.config.experimental.VirtualDeviceConfiguration(memory_limit=vram)])
#   except RuntimeError as e:
#     print(e)
import time
from pathlib import Path

import cv2
import torch
import torch.backends.cudnn as cudnn
from numpy import random

from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box ,plot_only_text,plot_one_box_notext
from utils.torch_utils import select_device, load_classifier, time_synchronized, TracedModel

class classify():
    def detect(save_img=False,opt = None):
        source, weights, view_img, save_txt, imgsz, trace = opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size, not opt.no_trace
        print(source, weights, view_img, save_txt, imgsz, trace)
        save_img = not opt.nosave and not source.endswith('.txt')  # save inference images
        save_txt = 1
        webcam = source.isnumeric() or source.endswith('.txt') or source.lower().startswith(
            ('rtsp://', 'rtmp://', 'http://', 'https://'))
        save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
        (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir
        set_logging()
        device = select_device(opt.device)
        half = device.type != 'cpu'  # half precision only supported on CUDA
        model = attempt_load(weights, map_location=device)  # load FP32 model
        stride = int(model.stride.max())  # model stride
        imgsz = check_img_size(imgsz, s=stride)  # check img_size
        if trace:
            model = TracedModel(model, device, opt.img_size)
        if half:
            model.half()  # to FP16
        classify = False
        if classify:
            modelc = load_classifier(name='resnet101', n=2)  # initialize
            modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()
        vid_path, vid_writer = None, None
        if webcam:
            view_img = check_imshow()
            cudnn.benchmark = True  # set True to speed up constant image size inference
            dataset = LoadStreams(source, img_size=imgsz, stride=stride)
        else:
            cudnn.benchmark = True
            dataset = LoadImages(source, img_size=imgsz, stride=stride)
        names = model.module.names if hasattr(model, 'module') else model.names
        colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]
        if device.type != 'cpu':
            model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
        old_img_w = old_img_h = imgsz
        old_img_b = 1
        t0 = time.time()
        mean_preds = []
        for path, img, im0s, vid_cap in dataset:
            img = torch.from_numpy(img).to(device)
            img = img.half() if half else img.float()  # uint8 to fp16/32
            img /= 255.0  # 0 - 255 to 0.0 - 1.0
            if img.ndimension() == 3:
                img = img.unsqueeze(0)
            if device.type != 'cpu' and (old_img_b != img.shape[0] or old_img_h != img.shape[2] or old_img_w != img.shape[3]):
                old_img_b = img.shape[0]
                old_img_h = img.shape[2]
                old_img_w = img.shape[3]
                for i in range(3):
                    model(img, augment=opt.augment)[0]
            # Inference
            t1 = time_synchronized()
            with torch.no_grad():   # Calculating gradients would cause a GPU memory leak
                pred = model(img, augment=opt.augment)[0]
            t2 = time_synchronized()
            # Apply NMS
            pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
            t3 = time_synchronized()
            # Apply Classifier
            if classify:
                pred = apply_classifier(pred, modelc, img, im0s)
            # Process detections
            for i, det in enumerate(pred):  # detections per image
                if webcam:  # batch_size >= 1
                    p, s, im0, frame = path[i], '%g: ' % i, im0s[i].copy(), dataset.count
                else:
                    p, s, im0, frame = path, '', im0s, getattr(dataset, 'frame', 0)

                p = Path(p)  # to Path
                save_path = str(save_dir / p.name)  # img.jpg
                txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
                # txt_path = str(save_dir /  p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
                gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
                obj_hole = []
                if len(det):
                    # Rescale boxes from img_size to im0 size
                    det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                    # Print results
                    for c in det[:, -1].unique():
                        n = (det[:, -1] == c).sum()  # detections per class
                        s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                    # Write results
                    i = 0
                    for *xyxyo, conf, cls in reversed(det): #改成xyxyo 因為我要用xyxy
                        if conf.item() > 0:#0.45 : #信心>0.45 才寫進去
                            if save_txt:  # Write to file
                                xywh = (xyxy2xywh(torch.tensor(xyxyo).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                                xyxy = xyxy2xywh_transfer([float(xywh[0]),float(xywh[1]),float(xywh[2]),float(xywh[3])],[640,480],'xywh2xyxy') #後+ 
                                line = (cls, *xywh, conf) if opt.save_conf else (cls, *xywh)  # label format
                                # print(conf.item())
                                # if conf.item() >0.45 : #信心>0.45 才寫進去
                                with open(txt_path + '.txt', 'a') as f:# with open(txt_path + '.txt', 'a') as f:
                                    f.write(('%g ' * len(line)).rstrip() % line + '\n')
                            obj_pc = ([round((xyxy[0]+xyxy[2])/2, 3),round((xyxy[1]+xyxy[3])/2, 3),0])
                            # print(obj_pc)
                            obj_hole.append(obj_pc)

                obj_hole = obj_hole
                if len(obj_hole) < 20  :
                    add_num = 20-len(obj_hole)
                    list(obj_hole)
                    # print(add_num)
                    for j in range(add_num):
                        obj_hole.append([0,0,0]) # 代表填充的
                obj = (np.array(obj_hole)).reshape(1,20,3)

                # print(obj_hole)
                preds = kmodel.predict(obj)
                topreds = np.argmax(preds, -1) ## 分類
                # print(topreds[0])
                mean_preds.append(topreds[0])

                mean_times = 5
                if len(mean_preds) >mean_times:
                    mean_preds.pop(0)
                maxlabel = max(mean_preds,key=mean_preds.count)
                # print(maxlabel)
                classs = class_names[maxlabel]

                # print(classs)
                #
                #
                # + 個低通filter 用list存10個class得平均
                #
                #
                cv2.putText(im0, str(classs), (40, 40), cv2.FONT_HERSHEY_PLAIN, 2.0, (0, 0, 255), 2)

                sop_dir = './Eclatorq/sop/labels/'+str(classs)+".txt"
                f = open(sop_dir)
                temp_sop_list = []
                temp_xmin=[]
                temp_ymin=[]
                temp_xmax=[]
                temp_ymax=[]
                for line in f.readlines():
                    #line = line.split(' ')
                    line = list(map(float, line.split(' ')))
                    temp_sop_list.append([line[0],line[1],line[2],line[3],line[4],line[5]]) # 順序 , 種類 , x center ,y center , w , h 
                    #load sop進來 下面比較 #######這邊要去改 抓物體後得比例 現在是影像的比例
                for *xyxyo, conf, cls in reversed(det): #改成xyxyo 因為我要用xyxy
                    xywh = (xyxy2xywh(torch.tensor(xyxyo).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                    xmin = xywh[0]-xywh[2]/2
                    ymin = xywh[1]-xywh[3]/2
                    xmax = xywh[0]+xywh[2]/2
                    ymax = xywh[1]+xywh[3]/2
                    temp_xmin.append(xmin)
                    temp_ymin.append(ymin)
                    temp_xmax.append(xmax)
                    temp_ymax.append(ymax)
                    #這邊只為了獲取obj大小 
                    # plot_one_box_notext(xyxyo, im0, label="", color=colors[int(cls)], line_thickness=3)
                if len(temp_xmin) > 0 :
                    objxmin = min(temp_xmin)*640
                    objymin = min(temp_ymin)*480
                    objxmax = max(temp_xmax)*640
                    objymax = max(temp_ymax)*480
                    tttt = [objxmin,objymin,objxmax,objymax] 
                    # print(tttt)
                    # plot_one_box(tttt, im0, label="obj", color=[255,0,0], line_thickness=1)
                
                for *xyxyo, conf, cls in reversed(det):
                    xywh = (xyxy2xywh(torch.tensor(xyxyo).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                    # print(xywh[0]*640,xywh[1]*480)
                    text = ""
                    find_range = 1.5
                    for i in range(len(temp_sop_list)):
                        xmin = (temp_sop_list[i][2]-temp_sop_list[i][4]/find_range)*(objxmax-objxmin)
                        ymin = (temp_sop_list[i][3]-temp_sop_list[i][5]/find_range)*(objymax-objymin)
                        xmax = (temp_sop_list[i][2]+temp_sop_list[i][4]/find_range)*(objxmax-objxmin)
                        ymax = (temp_sop_list[i][3]+temp_sop_list[i][5]/find_range)*(objymax-objymin)
                        t = [xmin+objxmin,ymin+objymin,xmax+objxmin,ymax+objymin]
                        # print(t)
                        # plot_one_box(t, im0, label="", color=[255,0,0], line_thickness=1)# 載入ㄉsop圖
                        if xmax+objxmin > xywh[0]*640 > xmin+objxmin and ymax+objymin>xywh[1]*480 > ymin+objymin: 
                            text = int(temp_sop_list[i][0])
                            label = str(text)
                            plot_one_box(xyxyo, im0, label=label, color=[0,0,255], line_thickness=3)#colors[int(cls)]
                    # label = str(text)
                    # plot_one_box(xyxyo, im0, label=label, color=[255,0,255], line_thickness=3)#colors[int(cls)]
                #'./yolov7/Eclatorq/images/'
                if view_img:
                    # print("video")
                    cv2.imshow(str(p), im0)
                    cv2.waitKey(1)  # 1 millisecond

                # Save results (image with detections)
                if save_img:
                    if dataset.mode == 'image':
                        cv2.imwrite(save_path, im0) #改這裡 可以改存的地方
                        print(f" The image with the result is saved in: {save_path}")
                    else:  # 'video' or 'stream'
                        if vid_path != save_path:  # new video
                            vid_path = save_path
                            if isinstance(vid_writer, cv2.VideoWriter):
                                vid_writer.release()  # release previous video writer
                            if vid_cap:  # video
                                fps = vid_cap.get(cv2.CAP_PROP_FPS)
                                w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                                h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            else:  # stream
                                fps, w, h = 30, im0.shape[1], im0.shape[0]
                                save_path += '.mp4'
                            vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                        vid_writer.write(im0)

        if save_txt or save_img:
            # s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ''
            print(f"Results saved to {save_dir}{s}")

        print(f'Done. ({time.time() - t0:.3f}s)')
        return  save_dir
filename = os.path.basename(__file__)
filename=filename[17:len(filename)-3]
print("filename :",filename)

NUM_POINTS = 2048
NUM_CLASSES = 10
history_list=[]
model_list=[]
preds_list=[]
class_names_list= []
label_list=[]
color = [[0.5,0,0],'b','g','r','y','k','c','m']
def xyxy2xywh_transfer(temp_xy,imgyx,mode):
    if mode == 'xyxy2xywh':
        xywh = [((temp_xy[0]+temp_xy[2])/2)/imgyx[0],((temp_xy[1]+temp_xy[3])/2)/imgyx[1],abs((temp_xy[0]-temp_xy[2])) /imgyx[0],abs((temp_xy[1]-temp_xy[3])) /imgyx[1]]
        return xywh
    elif mode == 'xywh2xyxy':
        xyxy = [(temp_xy[0]-temp_xy[2]/2)*imgyx[0] ,(temp_xy[1]-temp_xy[3]/2)*imgyx[1] , (temp_xy[0]+temp_xy[2]/2)*imgyx[0] , (temp_xy[1]+temp_xy[3]/2)*imgyx[1]]
        return xyxy
def load_dataset(DATA_DIR):
    print("load")
    train_points = []
    train_labels = []
    test_points = []
    test_labels = []
    class_names = []

    #return train_name
    save_name_p= "yolo_train_points.npy"
    save_name_l= "yolo_train_labels.npy"
    temp = os.path.join(DATA_DIR, "*")
    folders = glob.glob(temp)
    for i, folder in enumerate(folders):
        temp = os.path.basename(folder)
        print("processing class: {}".format(temp))
        class_names.append(temp)
        train_points = np.load(save_name_p, allow_pickle=True)
        train_labels = np.load(save_name_l, allow_pickle=True)
    class_names = np.array(class_names)
    return class_names,train_points,train_labels   

def conv_bn(x, filters):
    x = layers.Conv1D(filters, kernel_size=1, padding="valid")(x)
    x = layers.BatchNormalization(momentum=0.0)(x)
    return layers.Activation("relu")(x)
def dense_bn(x, filters):
    x = layers.Dense(filters)(x)
    x = layers.BatchNormalization(momentum=0.0)(x)
    return layers.Activation("relu")(x)
def tnet(inputs, num_features):
    # Initalise bias as the indentity matrix
    bias = tf.keras.initializers.Constant(np.eye(num_features).flatten())
    reg = OrthogonalRegularizer(num_features)

    x = conv_bn(inputs, 32)
    x = conv_bn(x, 64)
    x = conv_bn(x, 512)
    x = layers.GlobalMaxPooling1D()(x)
    x = dense_bn(x, 256)
    x = dense_bn(x, 128)
    x = layers.Dense(num_features * num_features, kernel_initializer="zeros", bias_initializer=bias,
                     activity_regularizer=reg, )(x)
    feat_T = layers.Reshape((num_features, num_features))(x)
    # Apply affine transformation to input features
    return layers.Dot(axes=(2, 1))([inputs, feat_T])
class OrthogonalRegularizer(tf.keras.regularizers.Regularizer):
    def __init__(self, num_features, l2reg=0.001):
        self.num_features = num_features
        self.l2reg = l2reg
        self.eye = tf.eye(num_features)

    def __call__(self, x):
        x = tf.reshape(x, (-1, self.num_features, self.num_features))
        xxt = tf.tensordot(x, x, axes=(2, 2))
        xxt = tf.reshape(xxt, (-1, self.num_features, self.num_features))
        return tf.reduce_sum(self.l2reg * tf.square(xxt - self.eye))



def classify2tensor ():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='best_200.pt', help='model.pt path(s)') # yolov7.pt
    parser.add_argument('--source', type=str, default='1', help='source')  # file/folder  inference/images  , 0 for webcam
    parser.add_argument('--img-size', type=int, default=160, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--no-trace', action='store_true', help='don`t trace model')
    opt = parser.parse_args()
    print(opt.source)
    cs.detect(opt) 

#fit_list = [x_train,x_train]


if __name__ == "__main__":
    cs = classify()
    DATA_DIR = "C:/Users/karta/OneDrive/桌面/one_pycharm/yolo"  # model 0 用10種 model 1 用5種

    class_names,train_points,train_labels = load_dataset(DATA_DIR)
    model_weights_name= '20230811'+'.h5' #
    inputs = tf.keras.Input(shape=(20, 3))
    x = tnet(inputs, 3)
    x = conv_bn(x, 32)
    x = conv_bn(x, 32)
    x = tnet(x, 32)
    x = conv_bn(x, 32)
    x = conv_bn(x, 64)
    x = conv_bn(x, 256)
    x = layers.GlobalMaxPooling1D()(x)
    x = dense_bn(x, 128)
    x = layers.Dropout(0.3)(x)
    x = dense_bn(x, 64)
    x = layers.Dropout(0.3)(x)

    outputs = layers.Dense(len(class_names), activation="softmax")(x)

    kmodel = tf.keras.Model(inputs=inputs, outputs=outputs, name="pointnet")
    # model.summary()
    optimizer = tf.keras.optimizers.Adam(learning_rate=0.001)
    kmodel.compile(loss="sparse_categorical_crossentropy", optimizer=optimizer, metrics=["sparse_categorical_accuracy"], )
    #model.fit(x_train, y_train, batch_size=batch_size, epochs=1, verbose=1)
    kmodel.load_weights(model_weights_name)
    classify2tensor()

# for i in range (model_num): # 
#     history = "history"+str(i)
#     model_save = "model"+str(i)
#     print(model_save)
#     model_list.append(model_save) 
#     model = eval("model"+str(i))
#     model_weights_name= filename+'_yolo_'+str(model_save)+'.h5'
#     #print(model_list)
#     class_names,train_points,train_labels = load_dataset(DATA_DIR[i])
#     x_train,x_test,y_train,y_test = Kfold_ramdom(train_points,train_labels,splits,666,87)
#     print(class_names)
#     if fit_tf == True :
#         history,preds,label= model(x_train,y_train,x_test,y_test,class_names,BATCH_SIZE_lsit[i],epochs,model_weights_name,fit_tf) #BATCH_SIZE,epochs
#         history_list.append(history)

#     elif fit_tf == False:
#         preds,label= model(x_train,y_train,x_test,y_test,class_names,BATCH_SIZE_lsit[i],epochs,model_weights_name,fit_tf) #BATCH_SIZE,epochs

#     buf_pr = preds##給後面顯示用
#     preds = np.argmax(preds, -1) ## 分類
#     label_list.append(label)
#     preds_list.append(preds)
#     class_names_list.append(class_names)
#     print(class_names_list)

# plot_confusion_matrix(label_list, preds_list, classes=class_names_list, normalize=False,title=model_list)
# try :
#     if fit_tf == True:
#         plot_history(history_list)
#         print("test")
# except ValueError:
#         pass
# plt.show()